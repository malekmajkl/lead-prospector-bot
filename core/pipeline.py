from __future__ import annotations

import logging
import time
from datetime import datetime

import anthropic

from core.claude_client import parse_json_response
from core.config import API_KEY, CREDS, SHEETS_ID, TODAY
from core.sheets import deduplicate, get_known_municipalities, save_to_sheets
from core.gmail_client import save_gmail_drafts
from core.xlsx import save_to_xlsx
from core.telegram import tg_send, tg_typing

log = logging.getLogger(__name__)

# ── Research system prompt ─────────────────────────────────────────────────────
RESEARCH_SYSTEM = """Jsi expert na výzkum kontaktů pro municipální sektor v České republice.
Najdi požadované kontakty pomocí web_search na oficiálních stránkách obcí.

Výstup MUSÍ být POUZE validní JSON array — žádný text před ani za, žádné backticky.
Každý objekt musí mít přesně tato pole (null pokud nenajdeš):
{
  "municipality": "název obce",
  "region": "název kraje",
  "contact_name": "celé jméno",
  "role": "funkce/titul",
  "email": "email nebo null",
  "phone": "telefon nebo null",
  "source_url": "URL zdroje",
  "language": "CZ"
}
Nikdy nevymýšlej kontaktní údaje. Preferuj osobní email před obecným."""

# ── Scoring tables ─────────────────────────────────────────────────────────────
ROLE_PTS: dict[str, int] = {
    "starosta": 30, "starostka": 30, "primátor": 30,
    "místostarosta": 25, "ředitel": 25, "ředitelka": 25,
    "it ředitel": 20, "it manager": 20, "vedoucí odboru": 18,
    "tajemník": 15, "tajemnice": 15, "referent": 10,
}
LARGE: set[str] = {
    "kroměříž", "zlín", "vsetín", "uherské hradiště", "otrokovice", "holešov",
    "uherský brod", "brno", "ostrava", "olomouc", "plzeň",
}
MEDIUM: set[str] = {
    "luhačovice", "vizovice", "valašské meziříčí", "rožnov pod radhoštěm",
    "uherský ostroh", "kunovice", "staré město", "bystřice pod hostýnem",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def score_lead(lead: dict) -> tuple[int, str]:
    role_l = (lead.get("role") or "").lower()
    rpts = next((v for k, v in ROLE_PTS.items() if k in role_l), 5)

    email = lead.get("email") or ""
    if "@" in email:
        dpts = 8 if any(x in email for x in ["info@", "podatelna@", "e-podatelna@"]) else 15
    else:
        dpts = 0
    if lead.get("phone"):
        dpts += 10
    if (lead.get("contact_name") or "").strip().count(" ") >= 1:
        dpts += 5

    muni = (lead.get("municipality") or "").lower().strip()
    spts = 25 if muni in LARGE else 20 if muni in MEDIUM else 10

    src = (lead.get("source_url") or "").lower()
    srcpts = 15 if (".cz" in src or ".eu" in src) else (7 if src else 2)

    total = rpts + dpts + spts + srcpts
    tier = (
        "🔴 High Priority" if total >= 75 else
        "🟡 Medium Priority" if total >= 50 else
        "🟢 Low Priority" if total >= 25 else
        "⚪ Deprioritise"
    )
    return total, tier


def draft_email(lead: dict) -> tuple[str, str]:
    name    = lead.get("contact_name", "")
    muni    = lead.get("municipality", "")
    role_l  = (lead.get("role") or "").lower()
    surname = name.split()[-1] if name else ""

    if any(x in role_l for x in ["starostka", "ředitelka", "tajemnice"]):
        salutation = f"Vážená paní {surname}"
    elif any(x in role_l for x in ["starosta", "ředitel", "tajemník", "primátor"]):
        salutation = f"Vážený pane {surname}"
    else:
        salutation = f"Vážená paní / Vážený pane {surname}"

    subject = f"Energetické úspory pro {muni} — SolarObec s.r.o."
    body = (
        f"{salutation},\n\n"
        f"dovoluji si Vás oslovit jménem SolarObec s.r.o. "
        f"Specializujeme se na energetické úspory a fotovoltaiku pro obce a města v ČR.\n\n"
        f"Obcím podobné velikosti jako {muni} pomáháme snižovat náklady na energie "
        f"o 30–60 % ročně a zajišťujeme kompletní administraci dotací z OPŽP "
        f"a modernizačního fondu — bez zátěže na Vašem úřadu.\n\n"
        f"Rád bych Vám možnosti krátce představil — stačí 20 minut online nebo osobně.\n\n"
        f"S pozdravem,\n"
        f"Jan Novák\n"
        f"Jednatel, SolarObec s.r.o.\n"
        f"jan.novak@solarobec.cz | +420 777 123 456"
    )
    return subject, body


def research_leads(role: str, region: str, count: int,
                   exclude_municipalities: list[str] | None = None) -> list[dict]:
    client = anthropic.Anthropic(api_key=API_KEY)
    exclude_note = ""
    if exclude_municipalities:
        exclude_note = f" Vynech tyto obce (již v databázi): {', '.join(exclude_municipalities)}."

    for attempt in range(3):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                system=RESEARCH_SYSTEM,
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
                messages=[{"role": "user", "content":
                    f"Najdi {count} kontaktů s rolí '{role}' v oblasti '{region}' v ČR."
                    f"{exclude_note} Vrať POUZE JSON array s {count} záznamy."}],
            )
            break
        except anthropic.RateLimitError:
            wait = 65 * (attempt + 1)
            log.warning(f"Rate limit — čekám {wait}s (pokus {attempt + 1}/3)")
            time.sleep(wait)
    else:
        log.error("Rate limit — všechny pokusy vyčerpány")
        return []

    raw = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    result = parse_json_response(raw)
    if isinstance(result, list):
        log.info(f"Research: {len(result)} leads found")
        return result[:count]
    return []


# ── Pipeline orchestrator ──────────────────────────────────────────────────────

def run_pipeline(chat_id: str, role: str, region: str, count: int) -> None:
    MAX_ROUNDS   = 5
    MAX_SEARCHED = 40

    try:
        tg_send(
            chat_id,
            f"🔍 *Spouštím pipeline...*\n"
            f"• Role: `{role}`\n• Oblast: `{region}`\n• Hledám: `{count}` nových\n\n"
            f"⏳ Prohledávám weby obcí, čekejte 1–2 minuty...",
        )
        tg_typing(chat_id)

        excluded_munis = get_known_municipalities()
        if excluded_munis:
            tg_send(chat_id, f"📋 Načteno *{len(excluded_munis)}* obcí z databáze — vyhnu se duplicitám od začátku.")

        all_new_leads: list[dict] = []
        total_searched = 0
        round_num      = 0

        while len(all_new_leads) < count and round_num < MAX_ROUNDS and total_searched < MAX_SEARCHED:
            round_num += 1
            needed = count - len(all_new_leads)

            if round_num > 1:
                tg_send(
                    chat_id,
                    f"🔄 *Kolo {round_num}* — hledám dalších `{needed}` nových leadů\n"
                    f"_(přeskočeno {len(excluded_munis)} již známých obcí)_\n"
                    f"⏳ Čekám 65s kvůli API limitu...",
                )
                time.sleep(65)
                tg_typing(chat_id)

            leads = research_leads(role, region, needed + 2, exclude_municipalities=list(excluded_munis))
            if not leads:
                tg_send(chat_id, "⚠️ Žádné další leady nenalezeny v této oblasti.")
                break

            total_searched += len(leads)

            for lead in leads:
                score, tier = score_lead(lead)
                lead["_score"] = score
                lead["_tier"]  = tier
                lead["_subject"], lead["_draft"] = draft_email(lead)
                excluded_munis.add(lead.get("municipality", "").strip())

            leads.sort(key=lambda x: x.get("_score", 0), reverse=True)

            new_leads, dupes = deduplicate(leads)
            if dupes and not new_leads:
                log.info(f"Kolo {round_num}: {len(dupes)} duplicit, zkouším dál...")
                continue

            all_new_leads.extend(new_leads)
            log.info(f"Kolo {round_num}: +{len(new_leads)} nových, celkem {len(all_new_leads)}/{count}")

        if not all_new_leads:
            tg_send(
                chat_id,
                f"📭 *Žádné nové leady*\n\n"
                f"Prohledáno {total_searched} obcí v `{region}` — vše je již v databázi.\n\n"
                f"💡 Zkuste jinou oblast nebo roli.",
            )
            return

        saved_sheets = save_to_sheets(all_new_leads)
        xlsx_path    = save_to_xlsx(all_new_leads)
        draft_count  = save_gmail_drafts(all_new_leads)

        n         = len(all_new_leads)
        today_fmt = datetime.now().strftime("%-d. %-m. %Y · %H:%M")
        lines = [
            f"✅ *{n} nových leadů nalezeno*" + (f" _(po {round_num} kolech)_" if round_num > 1 else ""),
            f"🔍 `{role}` | `{region}` | {today_fmt}",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for lead in all_new_leads:
            tier_icon = lead["_tier"].split()[0]
            lines.append(f"{tier_icon} *{lead.get('municipality', '?')}* — {lead.get('contact_name', '?')}")
        lines += [
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"💾 Sheets: *{saved_sheets}/{n}*  📬 Gmail: *{draft_count}/{n}*  📁 `{xlsx_path.name if xlsx_path else '—'}`",
            "_Detaily v Excel/Sheets_",
        ]
        tg_send(chat_id, "\n".join(lines))

    except Exception as e:
        log.exception("Pipeline error")
        tg_send(chat_id, f"❌ Chyba:\n`{str(e)}`")

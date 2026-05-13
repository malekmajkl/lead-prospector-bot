from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Load .env ─────────────────────────────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()

TOKEN     = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GMAIL_TOK = os.getenv("GMAIL_TOKEN_JSON", "gmail_token.json")
SHEETS_ID = os.getenv("SHEETS_ID", "")
CREDS     = os.getenv("GOOGLE_CREDS_JSON", "./service_account.json")
BASE_URL  = f"https://api.telegram.org/bot{TOKEN}"
TODAY     = date.today().isoformat()
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Startup checks ────────────────────────────────────────────────────────────
errors = []
if not TOKEN:   errors.append("❌ TELEGRAM_TOKEN chybí v .env")
if not API_KEY: errors.append("❌ ANTHROPIC_API_KEY chybí v .env")
if errors:
    for e in errors: print(e)
    sys.exit(1)



# ══════════════════════════════════════════════════════════════════════════════
# SKILL ENGINE — loads SKILL.md files and drives Claude API calls
# ══════════════════════════════════════════════════════════════════════════════

SKILLS_DIR = Path(os.getenv("SKILLS_DIR", str(Path(__file__).parent / "skills")))

def load_skill(name: str) -> str:
    """Load a SKILL.md file — searches local skills/ folder and ~/.openclaw/workspace/skills/"""
    candidates = [
        SKILLS_DIR / name / "SKILL.md",
        Path(__file__).parent / "skills" / name / "SKILL.md",
        Path.home() / ".openclaw" / "workspace" / "skills" / name / "SKILL.md",
    ]
    for path in candidates:
        if path.exists():
            log.info(f"Loaded skill: {name} ({path})")
            return path.read_text(encoding="utf-8")
    log.warning(f"Skill '{name}' not found — using built-in fallback")
    return ""


def call_claude(system: str, user_message: str,
                tools: list = None, max_tokens: int = 2000) -> str:
    """Call Claude API. Retries 3x on rate limit with exponential backoff."""
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)
    kwargs = dict(model="claude-sonnet-4-6", max_tokens=max_tokens,
                  system=system, messages=[{"role": "user", "content": user_message}])
    if tools:
        kwargs["tools"] = tools
    for attempt in range(3):
        try:
            response = client.messages.create(**kwargs)
            return "".join(b.text for b in response.content if hasattr(b, "text")).strip()
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 65 * (attempt + 1)
                log.warning(f"Rate limit — waiting {wait}s (attempt {attempt+1}/3)")
                time.sleep(wait)
            else:
                raise
    log.error("Rate limit — all retries exhausted"); return ""


def parse_json_response(raw: str):
    """Robustly extract JSON from Claude response."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    for pattern in [r"\[.*\]", r"\{.*\}"]:
        match = re.search(pattern, raw, re.DOTALL)
        if match:
            try: return json.loads(match.group(0))
            except json.JSONDecodeError: pass
    try: return json.loads(raw)
    except json.JSONDecodeError as e:
        log.error(f"JSON parse failed: {e}\nRaw: {raw[:200]}"); return None


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — LEAD RESEARCH (skill-driven)
# ══════════════════════════════════════════════════════════════════════════════

def research_leads(role: str, region: str, count: int,
                   exclude_municipalities: list = None) -> list:
    """Research leads using lead-researcher SKILL.md as system prompt."""
    skill = load_skill("lead-researcher")
    exclude_note = ""
    if exclude_municipalities:
        exclude_note = (f"\n\nIMPORTANT: Skip these municipalities (already in DB): "
                       f"{', '.join(exclude_municipalities)}. Find different ones.")
    system = (skill or "You are an expert at finding Czech municipal contacts.") + """

## CRITICAL OUTPUT REQUIREMENT
Return ONLY a valid JSON array — no markdown, no explanation, no backticks.
Each object must have: municipality, region, contact_name, role, email (or null),
phone (or null), source_url, language. Never invent contact details.
"""
    raw = call_claude(
        system=system,
        user_message=(f"Find {count} contacts with role '{role}' in '{region}', Czech Republic."
                      f"{exclude_note} Return ONLY JSON array with {count} entries."),
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        max_tokens=3000,
    )
    result = parse_json_response(raw)
    if isinstance(result, list):
        log.info(f"Research: {len(result)} leads found")
        return result[:count]
    return []


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — LEAD SCORING (skill-driven)
# ══════════════════════════════════════════════════════════════════════════════

def score_leads_batch(leads: list) -> list:
    """Score all leads in one Claude call using lead-scorer SKILL.md."""
    if not leads: return []
    skill = load_skill("lead-scorer")
    system = (skill or "Score leads 0-100: role seniority(30), data completeness(30), municipality size(25), source quality(15).") + """

## OUTPUT REQUIREMENT
Return ONLY a valid JSON array with ALL original fields plus:
  "_score": integer 0-100
  "_tier": "🔴 High Priority" | "🟡 Medium Priority" | "🟢 Low Priority" | "⚪ Deprioritise"
Return ALL leads in same order. No text, no backticks.
"""
    raw = call_claude(system=system, max_tokens=3000,
                      user_message=f"Score these {len(leads)} leads:\n{json.dumps(leads, ensure_ascii=False, indent=2)}")
    result = parse_json_response(raw)
    if isinstance(result, list) and len(result) == len(leads):
        log.info(f"Scored {len(result)} leads via skill")
        return sorted(result, key=lambda x: x.get("_score", 0), reverse=True)
    log.warning("Skill scoring failed — using built-in fallback")
    return sorted([_score_fallback(l) for l in leads], key=lambda x: x["_score"], reverse=True)


def _score_fallback(lead: dict) -> dict:
    ROLE_PTS = {"starosta":30,"starostka":30,"primátor":30,"místostarosta":25,
                "ředitel":25,"it ředitel":20,"vedoucí odboru":18,"tajemník":15,"referent":10}
    LARGE = {"kroměříž","zlín","vsetín","uherské hradiště","uherský brod","brno","ostrava","olomouc","plzeň","holešov"}
    MEDIUM = {"luhačovice","vizovice","valašské meziříčí","kunovice","staré město","uherský ostroh"}
    role_l = (lead.get("role") or "").lower()
    rpts = next((v for k,v in ROLE_PTS.items() if k in role_l), 5)
    email = lead.get("email") or ""
    dpts = (8 if any(x in email for x in ["info@","podatelna@","e-podatelna@"]) else 15) if "@" in email else 0
    if lead.get("phone"): dpts += 10
    if (lead.get("contact_name") or "").count(" ") >= 1: dpts += 5
    muni = (lead.get("municipality") or "").lower().strip()
    spts = 25 if muni in LARGE else 20 if muni in MEDIUM else 10
    src = (lead.get("source_url") or "").lower()
    srcpts = 15 if ".cz" in src or ".eu" in src else (7 if src else 2)
    total = rpts + dpts + spts + srcpts
    lead["_score"] = total
    lead["_tier"] = ("🔴 High Priority" if total >= 75 else "🟡 Medium Priority" if total >= 50
                     else "🟢 Low Priority" if total >= 25 else "⚪ Deprioritise")
    return lead


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — DRAFT EMAILS (skill-driven)
# ══════════════════════════════════════════════════════════════════════════════

def draft_emails_batch(leads: list) -> list:
    """Draft personalized emails for all leads using gmail-lead-drafter SKILL.md."""
    if not leads: return leads
    skill = load_skill("gmail-lead-drafter")
    system = (skill or "Draft personalized Czech cold-outreach emails for municipal contacts.") + """

## CEO PROFILE
Jméno: Jan Novák | Titul: Jednatel | Společnost: SolarObec s.r.o.
Email: jan.novak@solarobec.cz | Telefon: +420 777 123 456
Produkt: Energetické úspory, fotovoltaika a dotace z OPŽP pro obce.

## OUTPUT REQUIREMENT
Return ONLY a valid JSON array with ALL original fields plus:
  "_subject": personalized subject line
  "_draft": full email body (Czech, under 200 words, formal tone)
Return ALL leads. No text before or after. No backticks.
"""
    raw = call_claude(system=system, max_tokens=4000,
                      user_message=f"Draft emails for {len(leads)} leads:\n{json.dumps(leads, ensure_ascii=False, indent=2)}")
    result = parse_json_response(raw)
    if isinstance(result, list) and len(result) == len(leads):
        log.info(f"Drafted {len(result)} emails via skill")
        return result
    log.warning("Skill drafting failed — using built-in fallback")
    return [_draft_fallback(l) for l in leads]


def _draft_fallback(lead: dict) -> dict:
    name = lead.get("contact_name",""); muni = lead.get("municipality","")
    role_l = (lead.get("role") or "").lower()
    surname = name.split()[-1] if name else ""
    sal = (f"Vážená paní {surname}" if any(x in role_l for x in ["starostka","ředitelka","tajemnice"])
           else f"Vážený pane {surname}" if any(x in role_l for x in ["starosta","ředitel","tajemník"])
           else f"Vážená paní / Vážený pane {surname}")
    lead["_subject"] = f"Energetické úspory pro {muni} — SolarObec s.r.o."
    lead["_draft"] = (f"{sal},\n\ndovoluji si Vás oslovit jménem SolarObec s.r.o. "
                      f"Specializujeme se na energetické úspory a fotovoltaiku pro obce v ČR.\n\n"
                      f"Obcím jako {muni} pomáháme snižovat náklady na energie o 30–60 % ročně "
                      f"a zajišťujeme dotace z OPŽP a modernizačního fondu.\n\n"
                      f"Rád bych Vám vše krátce představil — stačí 20 minut.\n\n"
                      f"S pozdravem,\nJan Novák\nJednatel, SolarObec s.r.o.\n"
                      f"jan.novak@solarobec.cz | +420 777 123 456")
    return lead


# ══════════════════════════════════════════════════════════════════════════════
# TELEGRAM HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def tg_send(chat_id, text, parse_mode="Markdown"):
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        requests.post(f"{BASE_URL}/sendMessage", json={
            "chat_id": chat_id, "text": chunk, "parse_mode": parse_mode,
        }, timeout=15)
        time.sleep(0.3)

def tg_typing(chat_id):
    requests.post(f"{BASE_URL}/sendChatAction",
                  json={"chat_id": chat_id, "action": "typing"}, timeout=5)

def tg_updates(offset=None):
    r = requests.get(f"{BASE_URL}/getUpdates",
                     params={"timeout": 30, "offset": offset}, timeout=40)
    return r.json().get("result", []) if r.ok else []


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — LEAD RESEARCH
# ══════════════════════════════════════════════════════════════════════════════

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


def research_leads(role, region, count, exclude_municipalities=None):
    import anthropic
    client = anthropic.Anthropic(api_key=API_KEY)

    exclude_note = ""
    if exclude_municipalities:
        exclude_list = ", ".join(exclude_municipalities)
        exclude_note = f" Vynech tyto obce (již v databázi): {exclude_list}."

    # Retry with backoff on rate limit
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
            wait = 60 * (attempt + 1)
            log.warning(f"Rate limit — čekám {wait}s (pokus {attempt+1}/3)")
            time.sleep(wait)
    else:
        log.error("Rate limit — všechny pokusy vyčerpány")
        return []

    raw = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if match:
        try:
            leads = json.loads(match.group(0))
            if isinstance(leads, list):
                return leads[:count]
        except json.JSONDecodeError as e:
            log.error(f"JSON parse error: {e}")
    return []


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — SCORING
# ══════════════════════════════════════════════════════════════════════════════

ROLE_PTS = {
    "starosta": 30, "starostka": 30, "primátor": 30,
    "místostarosta": 25, "ředitel": 25, "ředitelka": 25,
    "it ředitel": 20, "it manager": 20, "vedoucí odboru": 18,
    "tajemník": 15, "tajemnice": 15, "referent": 10,
}
LARGE  = {"kroměříž","zlín","vsetín","uherské hradiště","otrokovice","holešov",
           "uherský brod","brno","ostrava","olomouc","plzeň"}
MEDIUM = {"luhačovice","vizovice","valašské meziříčí","rožnov pod radhoštěm",
          "uherský ostroh","kunovice","staré město","bystřice pod hostýnem"}

def score_lead(lead):
    role_l = (lead.get("role") or "").lower()
    rpts = next((v for k,v in ROLE_PTS.items() if k in role_l), 5)
    email = lead.get("email") or ""
    dpts = (8 if any(x in email for x in ["info@","podatelna@","e-podatelna@"]) else 15) if "@" in email else 0
    if lead.get("phone"): dpts += 10
    if (lead.get("contact_name") or "").strip().count(" ") >= 1: dpts += 5
    muni = (lead.get("municipality") or "").lower().strip()
    spts = 25 if muni in LARGE else 20 if muni in MEDIUM else 10
    src = (lead.get("source_url") or "").lower()
    srcpts = 15 if ".cz" in src or ".eu" in src else (7 if src else 2)
    total = rpts + dpts + spts + srcpts
    tier = ("🔴 High Priority" if total >= 75 else
            "🟡 Medium Priority" if total >= 50 else
            "🟢 Low Priority" if total >= 25 else "⚪ Deprioritise")
    return total, tier


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — DEDUPLICATION
# ══════════════════════════════════════════════════════════════════════════════

def deduplicate(leads):
    # Logic follows lead-deduplicator/SKILL.md (email > name+muni > phone priority)
    if not SHEETS_ID or not os.path.exists(CREDS):
        log.info("Sheets not configured — skipping dedup")
        return leads, []
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds  = Credentials.from_service_account_file(
            CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        ws     = client.open_by_key(SHEETS_ID).worksheet("Leads")
        rows   = ws.get_all_records()
        existing_emails = {r.get("Email","").lower().strip() for r in rows if r.get("Email")}
        existing_pairs  = {(r.get("Contact Name","").lower().strip(),
                            r.get("Municipality","").lower().strip()) for r in rows}
        new_leads, dupes = [], []
        for lead in leads:
            email = (lead.get("email") or "").lower().strip()
            name  = (lead.get("contact_name") or "").lower().strip()
            muni  = (lead.get("municipality") or "").lower().strip()
            if (email and email in existing_emails) or (name, muni) in existing_pairs:
                dupes.append(lead)
            else:
                new_leads.append(lead)
        log.info(f"Dedup: {len(new_leads)} new, {len(dupes)} duplicates")
        return new_leads, dupes
    except Exception as e:
        log.warning(f"Dedup error: {e}")
        return leads, []




def get_known_municipalities():
    """Load all municipality names already in Sheets DB — used to pre-exclude before search."""
    if not SHEETS_ID or not os.path.exists(CREDS):
        return set()
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds  = Credentials.from_service_account_file(
            CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        ws     = client.open_by_key(SHEETS_ID).worksheet(
                     os.getenv("SHEETS_TAB", "Leads"))
        rows   = ws.get_all_records()
        munis  = {r.get("Municipality","").strip() for r in rows if r.get("Municipality")}
        log.info(f"Pre-loaded {len(munis)} known municipalities from Sheets")
        return munis
    except Exception as e:
        log.warning(f"Could not pre-load municipalities: {e}")
        return set()

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — DRAFT EMAIL
# ══════════════════════════════════════════════════════════════════════════════

def draft_email(lead):
    name   = lead.get("contact_name", "")
    muni   = lead.get("municipality", "")
    role_l = (lead.get("role") or "").lower()
    surname = name.split()[-1] if name else ""

    if any(x in role_l for x in ["starostka","ředitelka","tajemnice"]):
        salutation = f"Vážená paní {surname}"
    elif any(x in role_l for x in ["starosta","ředitel","tajemník","primátor"]):
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


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — SAVE TO SHEETS
# ══════════════════════════════════════════════════════════════════════════════

COLUMNS = ["Date Found","Municipality","Region","Contact Name","Role / Title",
           "Email","Phone","Source URL","Language","Email Draft","Status",
           "CEO Notes","Score","Priority Tier"]

SHEET_HEADERS = ["Date Found","Municipality","Region","Contact Name","Role / Title",
                 "Email","Phone","Source URL","Language","Email Draft","Status",
                 "CEO Notes","Score","Priority Tier"]

def save_to_sheets(leads):
    # Logic follows sheets-lead-sync/SKILL.md (header check, append, status updates)
    if not SHEETS_ID or not os.path.exists(CREDS):
        return 0
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds  = Credentials.from_service_account_file(
            CREDS, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        client = gspread.authorize(creds)
        ws     = client.open_by_key(SHEETS_ID).worksheet(
                     os.getenv("SHEETS_TAB", "Leads"))

        # Ensure header row exists — prevents column shift bug
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != "Date Found":
            ws.insert_row(SHEET_HEADERS, index=1)
            log.info("Header row inserted into Sheets")

        saved = 0
        for lead in leads:
            row = [
                TODAY,
                lead.get("municipality",""),
                lead.get("region",""),
                lead.get("contact_name",""),
                lead.get("role",""),
                lead.get("email","") or "",
                lead.get("phone","") or "",
                lead.get("source_url",""),
                "CZ",
                lead.get("_draft",""),
                "New", "",
                str(lead.get("_score","")),
                lead.get("_tier",""),
            ]
            ws.append_row(row, value_input_option="USER_ENTERED",
                          table_range="A1")
            saved += 1
        log.info(f"Saved {saved} leads to Sheets")
        return saved
    except Exception as e:
        log.error(f"Sheets save error: {e}")
        return 0


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — SAVE TO XLSX (local backup)
# ══════════════════════════════════════════════════════════════════════════════

import requests

from core.config import API_KEY, CHAT_ID, CREDS, GMAIL_TOK, SHEETS_ID, TOKEN, validate_config
from core.handlers import dispatch
from core.telegram import tg_updates

log = logging.getLogger(__name__)


def main() -> None:
    validate_config()

    sheets_ok = bool(SHEETS_ID) and Path(CREDS).exists()
    gmail_ok  = Path(GMAIL_TOK).exists()

    print("\n" + "=" * 50)
    print("  CEO Assistant Bot")
    print(f"  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 50)
    print("✅ Telegram: připojeno")
    print("✅ Anthropic API: připojeno")
    print(f"{'✅' if sheets_ok else '⚠️ '} Google Sheets: {'připojeno' if sheets_ok else 'nepřipojeno'}")
    print(f"{'✅' if gmail_ok  else '⚠️ '} Gmail: {'připojeno' if gmail_ok else 'nepřipojeno'}")
    print("\n💬 Napište /hledej v Telegramu")
    print("   Zastavení: Ctrl+C\n")

    offset: int | None = None
    while True:
        try:
            for update in tg_updates(offset):
                offset = update["update_id"] + 1
                if "message" in update:
                    dispatch(update["message"])
        except KeyboardInterrupt:
            print("\n👋 Bot zastaven.")
            break
        except requests.exceptions.ConnectionError:
            log.warning("Connection error — retry in 5s")
            time.sleep(5)
        except Exception as e:
            log.exception(f"Polling error: {e}")
            time.sleep(3)


if __name__ == "__main__":
    main()

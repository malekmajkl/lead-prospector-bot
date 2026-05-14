from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials as SACredentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build

from core.config import CHAT_ID, CREDS, GMAIL_TOK, SHEETS_ID, SHEETS_TAB, TODAY
from core.pipeline import run_pipeline
from core.gmail_client import save_gmail_drafts
from core.sheets import find_lead, get_leads_for_redraft, mark_drafts_created, update_lead_status_in_sheets
from core.telegram import tg_send

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

STATUS_LABELS: dict[str, str] = {
    "sent":     "Sent",
    "replied":  "Replied",
    "reviewed": "Reviewed",
    "closed":   "Closed",
    "new":      "New",
}

STATUS_ICONS: dict[str, str] = {
    "New":      "🆕",
    "Reviewed": "👁",
    "Sent":     "📤",
    "Replied":  "💬",
    "Closed":   "✅",
}

WELCOME = """
👋 *CEO Assistant je připravený!*

*Vyhledávání leadů:*
`/hledej [role] [oblast] [počet]`
→ `/hledej starostové Kroměříž 5`

*Aktualizace statusu:*
`/sent [obec nebo příjmení]`
`/replied [obec nebo příjmení]`
`/reviewed [obec nebo příjmení]`
`/closed [obec nebo příjmení]`
→ `/sent holešov`  nebo  `/replied kubáník`

*Synchronizace:*
`/sync`    — Gmail ↔ Sheets auto-sync (Sent + Replied)
`/redraft` — vytvoř Gmail drafty pro leady bez draftu

*Přehled:*
`/status` — statistiky z databáze
`/leady`  — dnešní nové leady
`/help`   — nápověda
"""


def parse_hledej(text: str) -> tuple[str, str, int]:
    parts = text.strip().split()
    count = 5
    if parts and parts[-1].isdigit():
        count = min(int(parts.pop()), 10)
    region_kw = ["kraj", "kroměříž", "zlín", "brno", "ostrava", "olomouc",
                 "vsetín", "jihlava", "hradec", "pardubice", "hradiště", "brod"]
    split_at = next(
        (i for i, p in enumerate(parts) if any(k in p.lower() for k in region_kw)), None
    )
    if split_at and split_at > 0:
        role   = " ".join(parts[:split_at])
        region = " ".join(parts[split_at:])
    elif len(parts) >= 2:
        role   = parts[0]
        region = " ".join(parts[1:])
    else:
        role   = " ".join(parts) or "starosta"
        region = "Česká republika"
    return role.strip(), region.strip(), count


def handle_status(chat_id: str) -> None:
    if not SHEETS_ID or not os.path.exists(CREDS):
        tg_send(chat_id, "⚠️ Google Sheets není připojeno.\nNastavte `SHEETS_ID` a `GOOGLE_CREDS_JSON` v `.env`.")
        return
    try:
        creds  = SACredentials.from_service_account_file(CREDS, scopes=_SCOPES)
        client = gspread.authorize(creds)
        rows   = client.open_by_key(SHEETS_ID).worksheet(SHEETS_TAB).get_all_records()
        counts: dict[str, int] = {}
        for r in rows:
            s = r.get("Status", "").strip()
            counts[s] = counts.get(s, 0) + 1
        high   = sum(1 for r in rows if "High"   in r.get("Priority Tier", ""))
        medium = sum(1 for r in rows if "Medium" in r.get("Priority Tier", ""))
        tg_send(
            chat_id,
            f"📊 *Lead Database — Statistiky*\n\n"
            f"• Celkem: *{len(rows)}*\n"
            f"• 🆕 New: *{counts.get('New', 0)}*\n"
            f"• 👁 Reviewed: *{counts.get('Reviewed', 0)}*\n"
            f"• 📤 Sent: *{counts.get('Sent', 0)}*\n"
            f"• 💬 Replied: *{counts.get('Replied', 0)}*\n"
            f"• ✅ Closed: *{counts.get('Closed', 0)}*\n\n"
            f"• 🔴 High Priority: *{high}*\n"
            f"• 🟡 Medium Priority: *{medium}*",
        )
    except Exception as e:
        tg_send(chat_id, f"❌ Chyba při načítání Sheets:\n`{e}`")


def handle_leady(chat_id: str) -> None:
    if not SHEETS_ID or not os.path.exists(CREDS):
        tg_send(chat_id, "⚠️ Google Sheets není připojeno.")
        return
    try:
        creds = SACredentials.from_service_account_file(CREDS, scopes=_SCOPES)
        client = gspread.authorize(creds)
        rows  = client.open_by_key(SHEETS_ID).worksheet(SHEETS_TAB).get_all_records()
        today_leads = [
            r for r in rows
            if str(r.get("Date Found", "")) == TODAY and r.get("Status", "") == "New"
        ]
        if not today_leads:
            tg_send(chat_id, f"📭 Dnes ({TODAY}) žádné nové leady.")
            return
        lines = [f"📋 *Dnešní nové leady ({len(today_leads)})*\n"]
        for lead in today_leads:
            lines.append(
                f"🏛️ *{lead.get('Municipality', '?')}* — {lead.get('Contact Name', '?')}\n"
                f"   {lead.get('Priority Tier', '')} · Score: {lead.get('Score', '—')}\n"
                f"   📧 `{lead.get('Email', '—')}`\n"
            )
        tg_send(chat_id, "\n".join(lines))
    except Exception as e:
        tg_send(chat_id, f"❌ Chyba:\n`{e}`")


def handle_update_status(chat_id: str, cmd: str, args: str) -> None:
    if not args:
        tg_send(chat_id, f"⚠️ Zadej obec nebo příjmení.\n\nPříklad: `/{cmd} holešov`  nebo  `/{cmd} kubáník`")
        return
    if not SHEETS_ID or not os.path.exists(CREDS):
        tg_send(chat_id, "⚠️ Google Sheets není připojeno.")
        return

    new_status = STATUS_LABELS[cmd]
    icon       = STATUS_ICONS[new_status]
    matches    = find_lead(args)

    if not matches:
        tg_send(chat_id, f"❌ Lead *'{args}'* nenalezen v databázi.\n\nZkus jiný výraz nebo `/leady` pro výpis dnešních leadů.")
        return

    if len(matches) == 1:
        lead = matches[0]
        ok   = update_lead_status_in_sheets(lead["_row_index"], new_status)
        if ok:
            tg_send(
                chat_id,
                f"{icon} *Status aktualizován*\n\n"
                f"🏛️ {lead['Municipality']} — {lead['Contact Name']}\n"
                f"📧 {lead.get('Email', '—')}\n"
                f"Status: *{new_status}*",
            )
        else:
            tg_send(chat_id, "❌ Nepodařilo se aktualizovat Sheets. Zkus znovu.")
    else:
        lines = [f"🔍 Nalezeno *{len(matches)}* výsledků pro `{args}`:", "Upřesni dotaz:\n"]
        for m in matches[:8]:
            lines.append(f"• `/{cmd} {m['Municipality'].lower()}` — {m['Contact Name']} ({m.get('Status', '?')})")
        if len(matches) > 8:
            lines.append(f"_...a {len(matches) - 8} dalších_")
        tg_send(chat_id, "\n".join(lines))


def handle_sync(chat_id: str) -> None:
    if not SHEETS_ID or not os.path.exists(CREDS):
        tg_send(chat_id, "⚠️ Google Sheets není připojeno.")
        return
    if not os.path.exists(GMAIL_TOK):
        tg_send(chat_id, "⚠️ Gmail token nenalezen.")
        return

    tg_send(chat_id, "🔄 *Synchronizuji Gmail ↔ Sheets...*\n⏳ Čekejte prosím...")

    try:
        gmail = build("gmail", "v1", credentials=OAuthCredentials.from_authorized_user_file(GMAIL_TOK))

        sa  = SACredentials.from_service_account_file(CREDS, scopes=_SCOPES)
        gc  = gspread.authorize(sa)
        ws  = gc.open_by_key(SHEETS_ID).worksheet(SHEETS_TAB)
        rows = ws.get_all_records()

        email_to_row: dict = {}
        for i, row in enumerate(rows, start=2):
            email  = row.get("Email", "").strip().lower()
            status = row.get("Status", "").strip()
            if email and status in ("New", "Reviewed", "Sent"):
                email_to_row[email] = {
                    "row": i, "status": status,
                    "name": row.get("Contact Name", ""),
                    "muni": row.get("Municipality", ""),
                }

        if not email_to_row:
            tg_send(chat_id, "ℹ️ Žádné aktivní leady v Sheets k synchronizaci.")
            return

        sent_updates: list[dict]    = []
        replied_updates: list[dict] = []

        # Check Gmail Sent — last 30 days
        sent_result   = gmail.users().messages().list(userId="me", labelIds=["SENT"], maxResults=100, q="newer_than:30d").execute()
        sent_messages = sent_result.get("messages", [])

        for msg_ref in sent_messages:
            msg     = gmail.users().messages().get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["To", "Subject"]).execute()
            headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            to_raw  = headers.get("to", "")
            m       = re.search(r"<(.+?)>", to_raw)
            to_email = (m.group(1) if m else to_raw).strip().lower()
            if to_email in email_to_row and email_to_row[to_email]["status"] in ("New", "Reviewed"):
                sent_updates.append({"row": email_to_row[to_email]["row"], "email": to_email,
                                     "name": email_to_row[to_email]["name"], "muni": email_to_row[to_email]["muni"],
                                     "subject": headers.get("subject", "")})

        # Check Gmail Inbox for replies — batched in groups of 10
        lead_emails    = list(email_to_row.keys())
        inbox_messages: list = []
        for i in range(0, min(len(lead_emails), 50), 10):
            chunk  = lead_emails[i:i + 10]
            query  = "from:(" + " OR ".join(chunk) + ") newer_than:60d"
            result = gmail.users().messages().list(userId="me", labelIds=["INBOX"], maxResults=50, q=query).execute()
            inbox_messages.extend(result.get("messages", []))

        for msg_ref in inbox_messages:
            msg       = gmail.users().messages().get(userId="me", id=msg_ref["id"], format="metadata", metadataHeaders=["From", "Subject"]).execute()
            headers   = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
            from_raw  = headers.get("from", "")
            m         = re.search(r"<(.+?)>", from_raw)
            from_email = (m.group(1) if m else from_raw).strip().lower()
            if from_email in email_to_row:
                replied_updates.append({"row": email_to_row[from_email]["row"], "email": from_email,
                                        "name": email_to_row[from_email]["name"], "muni": email_to_row[from_email]["muni"],
                                        "subject": headers.get("subject", "")})

        # Apply updates — Replied takes priority over Sent
        replied_rows    = {u["row"] for u in replied_updates}
        updated_sent    = 0
        updated_replied = 0

        for u in sent_updates:
            if u["row"] not in replied_rows:
                ws.update_cell(u["row"], 11, "Sent")
                updated_sent += 1
                log.info(f"Sync: {u['muni']} → Sent")

        for u in replied_updates:
            ws.update_cell(u["row"], 11, "Replied")
            updated_replied += 1
            log.info(f"Sync: {u['muni']} → Replied")

        total = updated_sent + updated_replied
        if total == 0:
            tg_send(chat_id,
                "✅ *Sync dokončen — žádné změny*\n\n"
                f"Zkontrolováno {len(sent_messages)} odeslaných emailů a {len(inbox_messages)} odpovědí.\n"
                "_Vše je aktuální._")
            return

        lines = [f"✅ *Sync dokončen — {total} aktualizací*", "━━━━━━━━━━━━━━━━━━━━━━━━━"]
        if updated_sent:
            lines.append(f"\n📤 *Odesláno ({updated_sent}):*")
            for u in sent_updates:
                if u["row"] not in replied_rows:
                    lines.append(f"  📤 {u['muni']} — {u['name']}")
        if updated_replied:
            lines.append(f"\n💬 *Odpověděli ({updated_replied}):*")
            for u in replied_updates:
                lines.append(f"  💬 {u['muni']} — {u['name']}")
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━━━━",
                  f"_Sheets aktualizován · {datetime.now().strftime('%-d.%-m. %H:%M')}_"]
        tg_send(chat_id, "\n".join(lines))

    except Exception as e:
        log.exception("Sync error")
        tg_send(chat_id, f"❌ Chyba při synchronizaci:\n`{str(e)}`")


def handle_redraft(chat_id: str) -> None:
    tg_send(chat_id, "📬 *Redraft* — hledám leady bez draftu...\n⏳ Chvíli strpení...")
    leads = get_leads_for_redraft()
    if not leads:
        tg_send(
            chat_id,
            "📭 *Žádné leady k redraftování*\n\n"
            "_Všechny nové leady s emailem již mají draft, nebo žádné nenalezeny._",
        )
        return
    tg_send(chat_id, f"📋 Nalezeno *{len(leads)}* leadů bez draftu. Tvořím Gmail drafty...")
    drafted_emails = save_gmail_drafts(leads)

    if drafted_emails is None:
        tg_send(
            chat_id,
            "⚠️ *Gmail token je neplatný — drafty nebyly vytvořeny.*\n\n"
            "Spusťte na serveru:\n`python3 setup_gmail_auth.py`\n\n"
            "Poté zkuste `/redraft` znovu.",
        )
        return

    count = len(drafted_emails)
    mark_drafts_created(drafted_emails)
    tg_send(
        chat_id,
        f"✅ *{count}/{len(leads)}* Gmail draftů vytvořeno.\n\n"
        + (f"⚠️ {len(leads) - count} selhalo — zkontrolujte Gmail token." if count < len(leads) else ""),
    )


def dispatch(message: dict) -> None:
    chat_id = str(message["chat"]["id"])
    text    = message.get("text", "").strip()
    if CHAT_ID and chat_id != str(CHAT_ID):
        tg_send(chat_id, "⛔ Přístup odepřen.")
        return
    log.info(f"[{chat_id}] {text[:80]}")

    if text.startswith("/start") or text.startswith("/help"):
        tg_send(chat_id, WELCOME)
    elif text.startswith("/hledej"):
        args = text[len("/hledej"):].strip()
        if not args:
            tg_send(chat_id, "⚠️ Zadej roli a oblast.\n\nPříklad: `/hledej starostové Kroměříž 5`")
            return
        role, region, count = parse_hledej(args)
        run_pipeline(chat_id, role, region, count)
    elif text.startswith("/status"):
        handle_status(chat_id)
    elif text.startswith("/leady"):
        handle_leady(chat_id)
    elif text.startswith("/sync"):
        handle_sync(chat_id)
    elif text.startswith("/redraft"):
        handle_redraft(chat_id)
    elif any(text.startswith(f"/{cmd}") for cmd in STATUS_LABELS):
        parts = text.split(None, 1)
        cmd   = parts[0].lstrip("/").lower()
        args  = parts[1].strip() if len(parts) > 1 else ""
        handle_update_status(chat_id, cmd, args)
    else:
        tg_send(
            chat_id,
            "❓ Neznámý příkaz. Zkus `/help`.\n\n"
            "Rychlé tipy:\n"
            "`/hledej starostové Kroměříž 5`\n"
            "`/sent holešov`\n"
            "`/replied kubáník`",
        )

# CEO Assistant

Telegram bot that researches B2B leads in Czech municipalities, scores them, drafts personalised emails, and syncs status with Google Sheets and Gmail.

---

## Prerequisites

- Python 3.9+
- [Telegram bot token](https://t.me/BotFather) + your chat ID
- Anthropic API key (claude-sonnet-4-6 with `web_search` tool access)
- Google Cloud project with **Sheets API** and **Gmail API** enabled

---

## Setup

**1. Clone and install dependencies**

```bash
git clone https://github.com/malekmajkl/CEO_project.git
cd CEO_project
pip3 install -r requirements.txt
```

**2. Configure environment**

```bash
cp .env.example .env
# Fill in TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY,
# SHEETS_ID, GOOGLE_CREDS_JSON, GMAIL_TOKEN_JSON
```

**3. Set up Google Sheets** (service account)

Download your service account JSON from Google Cloud Console → save as `service_account.json` in the project folder. Share your Google Sheet with the service account email.

**4. Set up Gmail** (OAuth, one-time)

```bash
# Download OAuth client credentials from Google Cloud Console
# (APIs & Services → Credentials → OAuth client ID → Desktop app)
# Save as credentials.json in the project folder, then:
python3 setup_gmail_auth.py
```

**5. Start the bot**

```bash
./start.sh
# or directly:
python3 run_local.py
```

---

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/hledej [role] [oblast] [počet]` | Search for leads — e.g. `/hledej starostové Kroměříž 5` |
| `/status` | Lead database statistics |
| `/leady` | Today's new leads |
| `/sync` | Sync Gmail Sent/Inbox → update lead statuses in Sheets |
| `/redraft` | Create Gmail drafts for any leads that were never drafted |
| `/sent [obec/příjmení]` | Mark lead as Sent |
| `/replied [obec/příjmení]` | Mark lead as Replied |
| `/reviewed [obec/příjmení]` | Mark lead as Reviewed |
| `/closed [obec/příjmení]` | Mark lead as Closed |
| `/new [obec/příjmení]` | Reset lead status back to New |
| `/help` | Show all commands |

---

## Pipeline

`/hledej` runs the full pipeline:

1. **Research** — Claude searches municipal websites for contacts matching the role and region
2. **Score** — each lead scored 0–100 (role seniority, email quality, city size, source quality)
3. **Deduplicate** — skips leads already in Sheets
4. **Save** — writes to Google Sheets, exports Excel file, creates Gmail drafts
5. **Report** — sends summary to Telegram

---

## Gmail Token Expired?

If Gmail drafts fail with `invalid_grant`:

```bash
python3 setup_gmail_auth.py
```

Then send `/redraft` in Telegram to backfill drafts for any leads that were missed.

---

## Project Structure

```
CEO_project/
├── run_local.py          # Entry point
├── start.sh              # Start script
├── requirements.txt
├── setup_gmail_auth.py   # One-time Gmail OAuth setup
├── .env.example
├── core/
│   ├── config.py         # Env vars and constants
│   ├── pipeline.py       # Research, score, draft, run_pipeline
│   ├── handlers.py       # Telegram command handlers
│   ├── sheets.py         # Google Sheets read/write
│   ├── gmail_client.py   # Gmail draft creation
│   ├── xlsx.py           # Excel export
│   ├── telegram.py       # Telegram API helpers
│   └── claude_client.py  # Anthropic API wrapper
└── tests/
    ├── test_pipeline.py
    └── test_claude_client.py
```

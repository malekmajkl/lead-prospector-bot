# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Telegram bot (polling-based, not webhook) that researches B2B leads in Czech municipalities, scores them 0–100, generates personalised Czech cold-outreach emails, and syncs lead status between Google Sheets and Gmail.

## Commands

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run the bot
python3 run_local.py
# or via start.sh (also installs deps and checks required files)
./start.sh

# One-time Gmail OAuth setup (run locally, not on server)
python3 setup_gmail_auth.py

# Run all tests
pytest

# Run a single test file
pytest tests/test_pipeline.py

# Run a specific test class or method
pytest tests/test_pipeline.py::TestScoreLead::test_high_priority_mayor_large_city
```

## Architecture

### Core Data Flow

`/hledej` Telegram command → `handlers.dispatch()` → `pipeline.run_pipeline()`:

1. **Research** (`pipeline.research_leads`): Calls Claude API (`claude-sonnet-4-6`) with `web_search_20250305` tool. Returns JSON array of contacts. Retries up to 3× on `RateLimitError` with 65s backoff.
2. **Score** (`pipeline.score_lead`): Scores each lead 0–100 based on role seniority (`ROLE_PTS`), email type (personal > generic), city size (`LARGE`/`MEDIUM` sets), and source URL domain.
3. **Deduplicate** (`sheets.deduplicate`): Checks Sheets for duplicate emails or (name, municipality) pairs.
4. **Save**: `sheets.save_to_sheets()` → `xlsx.save_to_xlsx()` → `gmail_client.save_gmail_drafts()` → `sheets.mark_drafts_created()`.
5. **Report**: Sends summary to Telegram.

The pipeline loops up to 5 rounds (max 40 total researched) to reach the requested lead count, sleeping 65s between rounds to respect API rate limits.

### Module Responsibilities

| Module | Purpose |
|---|---|
| `core/config.py` | Loads `.env` manually (no dotenv lib), defines all constants. Imported first; side effects on import (creates `logs/`, `output/` dirs, configures logging). |
| `core/pipeline.py` | Research + scoring + email drafting logic. Contains hardcoded Czech role weights (`ROLE_PTS`) and known city lists (`LARGE`, `MEDIUM`). |
| `core/handlers.py` | Telegram command dispatch and per-command handlers. All commands route through `dispatch()`. Accesses Sheets with service-account auth directly (bypasses `sheets.py` for status updates). |
| `core/sheets.py` | Google Sheets CRUD via `gspread`. Sheet columns are positional — `Status` is column 11, `CEO Notes` is 12. |
| `core/gmail_client.py` | Gmail draft creation with OAuth. Auto-refreshes token and writes it back to disk. Returns `None` (sentinel `AUTH_REQUIRED`) on `invalid_grant` — callers must send a Telegram re-auth alert. |
| `core/claude_client.py` | Thin Anthropic SDK wrapper (`call_claude`). Also loads skill prompts from `skills/<name>/SKILL.md` via `load_skill()`. |
| `core/telegram.py` | Telegram API helpers (long-polling `getUpdates`, `sendMessage` with 4000-char chunking). |

### Authentication

Two separate Google auth paths:
- **Sheets**: Service account (`service_account.json`) — no expiry.
- **Gmail**: OAuth token (`gmail_token.json`) — expires, auto-refreshed in `_load_service()`. Re-run `setup_gmail_auth.py` if `invalid_grant`.

### Skills System

`skills/` contains SKILL.md files consumed by Claude Code (not by the bot itself). These define workflows for interactive Claude sessions (lead research + Gmail drafting via MCP). The bot's `claude_client.load_skill()` searches for skills in `SKILLS_DIR` (env var), then `./skills/`, then `~/.openclaw/workspace/skills/`.

## Key Constraints

- **Column positions in Sheets are hardcoded**: `handlers.py` writes directly to column 11 (Status) and 12 (CEO Notes) via `ws.update_cell(row, 11, status)`. If the sheet schema changes, update both `SHEET_HEADERS` in `sheets.py` and the hardcoded indices in `handlers.py`.
- **Rate limit handling**: The Anthropic API is called with `web_search_20250305` which can hit rate limits. All callers must handle `RateLimitError` with the 3-retry / 65s pattern already in `pipeline.py` and `claude_client.py`.
- **Email draft body is stored in Sheets**: The full email text goes into column 10 ("Email Draft") so `/redraft` can recreate Gmail drafts from Sheets without re-calling Claude.
- **`TELEGRAM_CHAT_ID` acts as an allowlist**: `dispatch()` rejects messages from any other chat ID if `CHAT_ID` is set.

## Environment Variables

See `.env.example`. Minimum required: `TELEGRAM_TOKEN`, `ANTHROPIC_API_KEY`. Optional but needed for full functionality: `SHEETS_ID`, `GOOGLE_CREDS_JSON` (Sheets), `GMAIL_TOKEN_JSON` (Gmail drafts), `TELEGRAM_CHAT_ID` (access control).

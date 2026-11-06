from __future__ import annotations

import logging
import os
import sys
from datetime import date
from pathlib import Path

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


def load_env() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())


load_env()

TOKEN      = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
API_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
GMAIL_TOK  = os.getenv("GMAIL_TOKEN_JSON", "gmail_token.json")
SHEETS_ID  = os.getenv("SHEETS_ID", "")
CREDS      = os.getenv("GOOGLE_CREDS_JSON", "./service_account.json")
SHEETS_TAB = os.getenv("SHEETS_TAB", "Leads")
BASE_URL   = f"https://api.telegram.org/bot{TOKEN}"
TODAY      = date.today().isoformat()
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)
SKILLS_DIR         = Path(os.getenv("SKILLS_DIR", str(Path(__file__).parent.parent / "skills")))
LLM_PROVIDER       = os.getenv("LLM_PROVIDER", "anthropic")
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")
LOCAL_LLM_MODEL    = os.getenv("LOCAL_LLM_MODEL", "llama3")
SEARCH_PROVIDER    = os.getenv("SEARCH_PROVIDER", "duckduckgo")
SERPAPI_KEY        = os.getenv("SERPAPI_KEY", "")


def validate_config() -> None:
    errors = []
    if not TOKEN:
        errors.append("❌ TELEGRAM_TOKEN chybí v .env")
    if LLM_PROVIDER == "anthropic" and not API_KEY:
        errors.append("❌ ANTHROPIC_API_KEY chybí v .env")
    if LLM_PROVIDER == "local" and SEARCH_PROVIDER == "serpapi" and not SERPAPI_KEY:
        errors.append("❌ SERPAPI_KEY chybí v .env (vyžadováno pro SEARCH_PROVIDER=serpapi)")
    if errors:
        for e in errors:
            print(e)
        sys.exit(1)

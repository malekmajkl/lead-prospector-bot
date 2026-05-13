from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

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

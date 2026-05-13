from __future__ import annotations

import logging
import time

import requests

from core.config import BASE_URL

log = logging.getLogger(__name__)


def tg_send(chat_id: str, text: str, parse_mode: str = "Markdown") -> None:
    for chunk in [text[i:i + 4000] for i in range(0, len(text), 4000)]:
        requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
            timeout=15,
        )
        time.sleep(0.3)


def tg_typing(chat_id: str) -> None:
    requests.post(
        f"{BASE_URL}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"},
        timeout=5,
    )


def tg_updates(offset: int | None = None) -> list:
    r = requests.get(
        f"{BASE_URL}/getUpdates",
        params={"timeout": 30, "offset": offset},
        timeout=40,
    )
    return r.json().get("result", []) if r.ok else []

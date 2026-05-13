from __future__ import annotations

import base64
import logging
from email.mime.text import MIMEText
from pathlib import Path

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from core.config import GMAIL_TOK

log = logging.getLogger(__name__)


def save_gmail_drafts(leads: list[dict]) -> int:
    tok = Path(GMAIL_TOK)
    if not tok.exists():
        log.warning(f"Gmail token not found: {tok}")
        return 0
    try:
        service = build("gmail", "v1", credentials=Credentials.from_authorized_user_file(str(tok)))
    except Exception as e:
        log.error(f"Gmail auth error: {e}")
        return 0

    saved = 0
    for lead in leads:
        to_email = lead.get("email") or ""
        if not to_email or "@" not in to_email:
            continue
        try:
            msg = MIMEText(lead["_draft"], "plain", "utf-8")
            msg["To"]      = to_email
            msg["Subject"] = lead["_subject"]
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            saved += 1
            log.info(f"Draft saved → {to_email}")
        except Exception as e:
            log.error(f"Draft failed for {to_email}: {e}")
    return saved

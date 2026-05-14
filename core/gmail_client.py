from __future__ import annotations

import base64
import json
import logging
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from core.config import GMAIL_TOK

log = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# Sentinel returned when re-auth is required (invalid_grant or similar hard failure)
AUTH_REQUIRED = None


def _load_service():
    """
    Load and return an authenticated Gmail service.

    Returns:
        service  — ready to use
        None     — hard auth failure (invalid_grant); caller should alert user
    Raises:
        FileNotFoundError — token file missing entirely
    """
    tok = Path(GMAIL_TOK)
    if not tok.exists():
        raise FileNotFoundError(f"Gmail token not found: {tok}")

    creds = Credentials.from_authorized_user_file(str(tok), _SCOPES)

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                tok.write_text(creds.to_json())
                log.info("Gmail token refreshed automatically")
            except Exception as e:
                if "invalid_grant" in str(e).lower():
                    log.error(f"Gmail token revoked (invalid_grant) — re-auth required: {e}")
                    return AUTH_REQUIRED
                raise
        else:
            log.error("Gmail token invalid and cannot be refreshed — re-auth required")
            return AUTH_REQUIRED

    return build("gmail", "v1", credentials=creds)


def save_gmail_drafts(leads: list[dict]) -> list[str] | None:
    """
    Create Gmail drafts for leads.

    Returns:
        list[str]  — emails successfully drafted (empty list = token ok, no emails to draft)
        None       — hard auth failure; caller should send a Telegram re-auth alert
    """
    try:
        service = _load_service()
    except FileNotFoundError as e:
        log.warning(str(e))
        return []

    if service is AUTH_REQUIRED:
        return AUTH_REQUIRED

    drafted: list[str] = []
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
            drafted.append(to_email)
            log.info(f"Draft saved → {to_email}")
        except Exception as e:
            log.error(f"Draft failed for {to_email}: {e}")
    return drafted

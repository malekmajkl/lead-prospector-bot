from __future__ import annotations

import logging
import os
import unicodedata

import gspread
from google.oauth2.service_account import Credentials

from core.config import CREDS, SHEETS_ID, SHEETS_TAB, TODAY

log = logging.getLogger(__name__)

SHEET_HEADERS = [
    "Date Found", "Municipality", "Region", "Contact Name", "Role / Title",
    "Email", "Phone", "Source URL", "Language", "Email Draft", "Status",
    "CEO Notes", "Score", "Priority Tier", "Draft Created",
]

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _get_worksheet():
    creds = Credentials.from_service_account_file(CREDS, scopes=_SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEETS_ID).worksheet(SHEETS_TAB)


def _sheets_available() -> bool:
    return bool(SHEETS_ID) and os.path.exists(CREDS)


def get_known_municipalities() -> set[str]:
    if not _sheets_available():
        return set()
    try:
        ws   = _get_worksheet()
        rows = ws.get_all_records()
        munis = {r.get("Municipality", "").strip() for r in rows if r.get("Municipality")}
        log.info(f"Pre-loaded {len(munis)} known municipalities from Sheets")
        return munis
    except Exception as e:
        log.warning(f"Could not pre-load municipalities: {e}")
        return set()


def deduplicate(leads: list[dict]) -> tuple[list[dict], list[dict]]:
    if not _sheets_available():
        log.info("Sheets not configured — skipping dedup")
        return leads, []
    try:
        ws   = _get_worksheet()
        rows = ws.get_all_records()
        existing_emails = {r.get("Email", "").lower().strip() for r in rows if r.get("Email")}
        existing_pairs  = {
            (r.get("Contact Name", "").lower().strip(), r.get("Municipality", "").lower().strip())
            for r in rows
        }
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


def save_to_sheets(leads: list[dict]) -> int:
    if not _sheets_available():
        return 0
    try:
        ws = _get_worksheet()
        first_row = ws.row_values(1)
        if not first_row or first_row[0] != "Date Found":
            ws.insert_row(SHEET_HEADERS, index=1)
            log.info("Header row inserted into Sheets")
        saved = 0
        for lead in leads:
            row = [
                TODAY,
                lead.get("municipality", ""),
                lead.get("region", ""),
                lead.get("contact_name", ""),
                lead.get("role", ""),
                lead.get("email", "") or "",
                lead.get("phone", "") or "",
                lead.get("source_url", ""),
                "CZ",
                lead.get("_draft", ""),
                "New", "",
                str(lead.get("_score", "")),
                lead.get("_tier", ""),
                "",  # Draft Created — filled by mark_drafts_created() after Gmail draft is saved
            ]
            ws.append_row(row, value_input_option="USER_ENTERED", table_range="A1")
            saved += 1
        log.info(f"Saved {saved} leads to Sheets")
        return saved
    except Exception as e:
        log.error(f"Sheets save error: {e}")
        return 0


def get_leads_for_redraft() -> list[dict]:
    """Return New leads with an email — used by /redraft to backfill missing Gmail drafts."""
    if not _sheets_available():
        return []
    try:
        ws   = _get_worksheet()
        rows = ws.get_all_records()
        leads = []
        for row in rows:
            email         = (row.get("Email") or "").strip()
            status        = (row.get("Status") or "").strip()
            draft_created = (row.get("Draft Created") or "").strip()
            if email and "@" in email and status == "New" and not draft_created:
                muni = row.get("Municipality", "")
                leads.append({
                    "municipality":  muni,
                    "contact_name":  row.get("Contact Name", ""),
                    "role":          row.get("Role / Title", ""),
                    "email":         email,
                    "_draft":        row.get("Email Draft", ""),
                    "_subject":      f"Energetické úspory pro {muni} — SolarObec s.r.o.",
                })
        log.info(f"Redraft: {len(leads)} eligible leads (never drafted)")
        return leads
    except Exception as e:
        log.error(f"get_leads_for_redraft error: {e}")
        return []


def mark_drafts_created(emails: list[str]) -> None:
    """Set 'Draft Created' = 'Yes' (col 15) for each successfully drafted email."""
    if not _sheets_available() or not emails:
        return
    try:
        ws        = _get_worksheet()
        rows      = ws.get_all_records()
        email_set = {e.lower() for e in emails}
        for i, row in enumerate(rows, start=2):
            if (row.get("Email") or "").lower() in email_set:
                ws.update_cell(i, 15, "Yes")
        log.info(f"Marked {len(emails)} leads as Draft Created")
    except Exception as e:
        log.error(f"mark_drafts_created error: {e}")


def find_lead(query: str) -> list[dict]:
    if not _sheets_available():
        return []
    try:
        ws   = _get_worksheet()
        rows = ws.get_all_records()

        def strip_diacritics(s: str) -> str:
            return "".join(
                c for c in unicodedata.normalize("NFD", s)
                if unicodedata.category(c) != "Mn"
            ).lower()

        q_norm = strip_diacritics(query.strip())
        matches = []
        for i, row in enumerate(rows, start=2):
            muni = strip_diacritics(row.get("Municipality", ""))
            name = strip_diacritics(row.get("Contact Name", ""))
            if q_norm in muni or q_norm in name:
                row["_row_index"] = i
                matches.append(row)
        return matches
    except Exception as e:
        log.error(f"find_lead error: {e}")
        return []


def update_lead_status_in_sheets(row_index: int, status: str, notes: str = "") -> bool:
    if not _sheets_available():
        return False
    try:
        ws = _get_worksheet()
        ws.update_cell(row_index, 11, status)
        if notes:
            ws.update_cell(row_index, 12, notes)
        log.info(f"Row {row_index} status → {status}")
        return True
    except Exception as e:
        log.error(f"update_lead_status error: {e}")
        return False

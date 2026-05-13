#!/usr/bin/env python3
"""
setup_gmail_auth.py — Jednorázové nastavení Gmail OAuth tokenu
==============================================================
Spusťte tento skript JEDNOU na Vašem počítači.
Otevře prohlížeč, přihlásíte se ke Google, udělíte souhlas
a skript uloží gmail_token.json pro trvalé použití.

Použití:
    python setup_gmail_auth.py

Předpoklad:
    Stažený OAuth credentials soubor z Google Cloud Console
    (pojmenujte ho credentials.json a dejte do stejné složky)
"""

import os
import sys
import json

# ── Dependency check ──────────────────────────────────────────────────────────
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ImportError:
    print("📦 Instaluji potřebné knihovny...")
    os.system(
        "pip3 install google-auth google-auth-oauthlib "
        "google-auth-httplib2 google-api-python-client"
    )
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

# ── Config ────────────────────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/gmail.compose",   # create/send drafts
    "https://www.googleapis.com/auth/gmail.readonly",  # read for dedup check
]

CREDENTIALS_FILE = "gmail_token.json"   # stažený z Google Cloud Console
TOKEN_FILE       = "gmail_token.json"   # výstup tohoto skriptu


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*55)
    print("  CEO Assistant — Gmail OAuth Setup")
    print("="*55 + "\n")

    # 1. Check credentials file exists
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"❌ Soubor '{CREDENTIALS_FILE}' nenalezen!\n")
        print("Postup jak ho získat:")
        print("  1. Jděte na https://console.cloud.google.com")
        print("  2. Vyberte nebo vytvořte projekt")
        print("  3. APIs & Services → Enable APIs → Gmail API → Enable")
        print("  4. APIs & Services → Credentials → Create Credentials")
        print("     → OAuth client ID → Desktop app → Create")
        print("  5. Stáhněte JSON → přejmenujte na 'credentials.json'")
        print("  6. Dejte credentials.json do stejné složky jako tento skript")
        print("  7. Spusťte znovu: python setup_gmail_auth.py\n")
        sys.exit(1)

    # 2. Check if token already exists and is valid
    # creds = None
    # if os.path.exists(TOKEN_FILE):
    #     creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # if creds and creds.valid:
    #     print(f"✅ Token již existuje a je platný: {TOKEN_FILE}")
    #     _verify_token(creds)
    #     return

    # # 3. Refresh if expired
    # if creds and creds.expired and creds.refresh_token:
    #     print("🔄 Token vypršel — obnovuji...")
    #     creds.refresh(Request())
    #     _save_token(creds)
    #     print("✅ Token obnoven.")
    #     _verify_token(creds)
    #     return

    # 4. Full OAuth flow — opens browser
    print("🌐 Otevírám prohlížeč pro přihlášení ke Google...\n")
    print("  → Přihlaste se ke Google účtu spojenému s Gmail")
    print("  → Klikněte 'Povolit' / 'Allow' pro všechna požadovaná oprávnění")
    print("  → Po úspěšném přihlášení se vraťte do terminálu\n")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)

    # Try local server first (better UX), fall back to console
    try:
        creds = flow.run_local_server(
            port=8080,
            prompt="consent",
            access_type="offline",
            success_message=(
                "✅ Přihlášení úspěšné! Můžete zavřít tuto záložku a vrátit se do terminálu."
            ),
        )
    except OSError:
        # Port 8080 busy — try another
        try:
            creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
        except Exception:
            # Fallback: manual code entry
            print("⚠️ Automatický flow selhal — použiji manuální kód.\n")
            creds = flow.run_console()

    # 5. Save token
    _save_token(creds)
    print(f"\n✅ Token úspěšně uložen: {TOKEN_FILE}\n")

    # 6. Verify by fetching Gmail profile
    _verify_token(creds)

    # 7. Show next steps
    print("\n" + "="*55)
    print("  Hotovo! Nastavte proměnnou prostředí:")
    print(f'  export GMAIL_TOKEN_JSON="{os.path.abspath(TOKEN_FILE)}"')
    print("\n  Nebo přidejte do .env souboru:")
    print(f'  GMAIL_TOKEN_JSON={os.path.abspath(TOKEN_FILE)}')
    print("="*55 + "\n")


def _save_token(creds):
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())


def _verify_token(creds):
    """Quick verification — fetch Gmail profile to confirm token works."""
    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email   = profile.get("emailAddress", "?")
        total   = profile.get("messagesTotal", "?")
        print(f"✅ Gmail ověřen: {email}")
        print(f"   Celkem zpráv v inboxu: {total}")
        print(f"   Oprávnění: compose + readonly ✓")
    except Exception as e:
        print(f"⚠️ Verifikace selhala: {e}")
        print("   Token byl uložen, ale zkontrolujte oprávnění.")


if __name__ == "__main__":
    main()

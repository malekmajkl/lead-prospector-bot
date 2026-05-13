#!/bin/bash
# start.sh — Spustí CEO Assistant Telegram Bot
# Použití: chmod +x start.sh && ./start.sh

set -e

if [ ! -f .env ]; then
  echo "❌ .env soubor nenalezen!"
  echo "   Stáhněte .env ze Claude a doplňte ANTHROPIC_API_KEY"
  exit 1
fi

[ ! -f service_account.json ] && echo "⚠️  service_account.json nenalezen — Google Sheets nebude aktivní"
[ ! -f gmail_token.json ]     && echo "⚠️  gmail_token.json nenalezen — spusťte: python setup_gmail_auth.py"

mkdir -p logs output

echo "📦 Instaluji závislosti..."
pip3 install -r requirements.txt -q

echo ""
echo "🤖 Spouštím CEO Assistant Bot..."
echo "   Napište /hledej v Telegramu | Zastavení: Ctrl+C"
echo ""

python3 run_local.py
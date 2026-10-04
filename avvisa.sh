#!/usr/bin/env bash
# Manda un messaggio sul bot Telegram. Uso: ./avvisa.sh "testo"
# Se il bot non è configurato, scrive solo nel diario.
echo "$1"
[ -n "${TELEGRAM_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ] || exit 0
curl -s -o /dev/null --max-time 30 "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$1" || true

#!/usr/bin/env bash
# Copia la puntata su Google Drive, con la stessa logica della cartella locale:
#   AI Paper in Pillole/OGGI   la puntata di oggi, completa (wav compreso)
#   AI Paper in Pillole/OLD    una cartella per ogni puntata passata, senza wav
# Usa rclone con il collegamento "gdrive" (configurato nel segreto RCLONE_CONF).
set -euo pipefail
ORIGINE="${1:-uscita/OGGI}"
BASE="gdrive:${DRIVE_CARTELLA:-AI Paper in Pillole}"
NOME=$(basename "$(ls -d archivio/puntate/*/ | tail -1)")

# 1. La puntata precedente passa da OGGI a OLD, senza il wav.
if PRIMA=$(rclone cat "$BASE/OGGI/nome_puntata.txt" 2>/dev/null) && [ -n "$PRIMA" ]; then
  if [ "$PRIMA" != "$NOME" ]; then
    echo "Archivio su Drive: $PRIMA → OLD (senza wav)"
    rclone delete "$BASE/OGGI" --include "*.wav"
    rclone move "$BASE/OGGI" "$BASE/OLD/$PRIMA" --exclude "nome_puntata.txt"
    rclone delete "$BASE/OGGI" --include "nome_puntata.txt"
  fi
fi

# 2. La puntata nuova in OGGI.
echo "Carico su Drive: $NOME"
rclone copy "$ORIGINE" "$BASE/OGGI" --exclude ".lavoro/**" --exclude "*.log" --stats-one-line --stats 10s -v
echo -n "$NOME" | rclone rcat "$BASE/OGGI/nome_puntata.txt"
echo "Drive aggiornato."

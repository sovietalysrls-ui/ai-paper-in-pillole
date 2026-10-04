#!/usr/bin/env python3
"""Pubblica (in bozza o subito, secondo config.yaml) l'articolo di una
puntata già archiviata, senza rifare la puntata.

Uso:
  python pubblica_articolo.py archivio/puntate/2026-10-03_050_onestreamer
  python pubblica_articolo.py ultima        la puntata più recente dell'archivio

Opzioni:
  --tentativo N     scrive nel messaggio Telegram quale tentativo è
  --ultimo          è l'ultimo tentativo: se fallisce, avvisa su Telegram
"""
import argparse
import os

import requests
import json
import re
import sys
from pathlib import Path

from kit.util import RADICE, carica_config
from kit.wordpress import ErroreWordPress, WordPress


def telegram(testo):
    token, chat = os.environ.get("TELEGRAM_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if token and chat:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=15,
                          json={"chat_id": chat, "text": testo})
        except requests.RequestException:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella")
    ap.add_argument("--tentativo", type=int, default=1)
    ap.add_argument("--sostituisci", action="store_true", help="aggiorna l'articolo se esiste già")
    ap.add_argument("--ultimo", action="store_true")
    a = ap.parse_args()
    cfg = carica_config(cloud=True)
    if a.cartella == "ultima":
        cartelle = sorted((cfg["archivio_git"] / "puntate").iterdir())
        d = cartelle[-1]
    else:
        d = Path(a.cartella)
        d = d if d.is_absolute() else RADICE / d
    if (d / "wordpress.json").exists():
        print("Articolo già pubblicato: " + (d / "wordpress.json").read_text(encoding="utf-8"))
        return 0
    html = (d / "articolo.html").read_text(encoding="utf-8")
    meta_p = d / "articolo_meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    else:
        f_tit = d / "titolo_e_descrizione.txt" if (d / "titolo_e_descrizione.txt").exists() else d / "titolo.txt"
        titolo = f_tit.read_text(encoding="utf-8").strip().splitlines()[0].split(" - ", 1)[-1]
        primo = re.search(r"<p>(.*?)</p>", html, re.S)
        testo = re.sub(r"<[^>]+>", "", primo.group(1)) if primo else ""
        estratto = " ".join(re.split(r"(?<=[.!?])\s+", testo)[:2])
        sk = json.loads((d / "scheda.json").read_text(encoding="utf-8")) if (d / "scheda.json").exists() else {}
        meta = {"titolo": titolo, "estratto": estratto, "tag": sk.get("hashtag", []),
                "categoria": cfg["wordpress"]["categoria"]}
    chiave = re.search(r"arxiv\.org/abs/([\w.]+)", html)
    chiave = chiave.group(1) if chiave else meta["titolo"]
    wp = WordPress(cfg["wordpress"]["sito"])
    try:
        r = wp.pubblica(meta["titolo"], html, meta["estratto"], meta.get("categoria", cfg["wordpress"]["categoria"]),
                        meta.get("tag", []), d / "copertina.jpg", cfg["wordpress"]["stato"], chiave,
                        sostituisci=a.sostituisci)
    except ErroreWordPress as e:
        print(f"WordPress (tentativo {a.tentativo}): {e}")
        if a.ultimo:
            telegram(f"⚠️ Articolo non caricato sul sito dopo {a.tentativo} tentativi: il server di Tophost "
                     f"blocca i server di GitHub usati stanotte. L'articolo è nell'archivio "
                     f"({d.name}). Per riprovare: Actions > Notte > Run workflow, con 'solo articolo'.")
        else:
            telegram(f"⏳ Articolo: tentativo {a.tentativo} non riuscito (il sito non risponde a questo server). "
                     f"Riprovo tra 15 minuti da un altro server.")
        return 1
    (d / "wordpress.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    stato = "in bozza" if r["stato"] == "draft" else r["stato"]
    print(("Già presente: " if r["esisteva"] else "Fatto: ") + f"{r['stato']} · {r.get('link', '')}")
    if a.tentativo > 1 or not r["esisteva"]:
        telegram(f"📝 Articolo sul sito {stato} (tentativo {a.tentativo}).\n{r.get('link', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

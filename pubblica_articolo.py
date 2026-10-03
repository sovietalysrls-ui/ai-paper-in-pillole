#!/usr/bin/env python3
"""Pubblica (in bozza o subito, secondo config.yaml) l'articolo di una
puntata già archiviata, senza rifare la puntata.

Uso:
  python pubblica_articolo.py archivio/puntate/2026-10-03_050_onestreamer
  python pubblica_articolo.py ultima        la puntata più recente dell'archivio
"""
import json
import re
import sys
from pathlib import Path

from kit.util import RADICE, carica_config
from kit.wordpress import ErroreWordPress, WordPress


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cfg = carica_config(cloud=True)
    if sys.argv[1] == "ultima":
        cartelle = sorted((cfg["archivio_git"] / "puntate").iterdir())
        d = cartelle[-1]
    else:
        d = Path(sys.argv[1])
        d = d if d.is_absolute() else RADICE / d
    html = (d / "articolo.html").read_text(encoding="utf-8")
    meta_p = d / "articolo_meta.json"
    if meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    else:
        titolo = (d / "titolo.txt").read_text(encoding="utf-8").strip().split(" - ", 1)[-1]
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
                        meta.get("tag", []), d / "copertina.jpg", cfg["wordpress"]["stato"], chiave)
    except ErroreWordPress as e:
        print(f"WordPress: {e}")
        return 1
    (d / "wordpress.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    print(("Già presente: " if r["esisteva"] else "Fatto: ") + f"{r['stato']} · {r.get('link', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

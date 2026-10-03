"""Cartella OGGI e archivio OLD."""
import shutil
from pathlib import Path

from .util import leggi_json, slug


def cartelle(cfg):
    base = cfg["cartella_base"]
    oggi = base / "OGGI"
    old = base / "OLD"
    for c in (base, oggi, old, base / "dati"):
        c.mkdir(parents=True, exist_ok=True)
    return base, oggi, old


def archivia_se_vecchia(oggi_dir, old_dir, data_oggi, scrivi):
    """Se OGGI contiene una puntata di un altro giorno, la sposta in OLD.

    Il wav non viene archiviato: è grande e l'mp3 fa da copia.
    Ritorna True se OGGI contiene già il lavoro di oggi (da riprendere).
    """
    stato_p = oggi_dir / ".lavoro" / "stato.json"
    contenuto = [p for p in oggi_dir.iterdir()]
    if not contenuto:
        return False
    stato = leggi_json(stato_p) if stato_p.exists() else {}
    if stato.get("data") == data_oggi:
        return True

    data = stato.get("data", "senza-data")
    numero = stato.get("numero")
    nome = f"{data}_#{numero}_{slug(stato.get('nome_breve', 'puntata'))}" if numero else f"{data}_puntata"
    if not stato.get("completa"):
        nome += "_INCOMPLETA"
    dest = old_dir / nome
    i = 2
    while dest.exists():
        dest = old_dir / f"{nome}_{i}"
        i += 1
    dest.mkdir(parents=True)
    tolti = 0
    for p in contenuto:
        for wav in ([p] if p.is_file() else p.rglob("*")):
            if wav.is_file() and wav.suffix.lower() == ".wav":
                wav.unlink()
                tolti += 1
        shutil.move(str(p), dest / p.name)
    scrivi(f"Puntata precedente archiviata in OLD/{dest.name} (wav tolti: {tolti})")
    return False

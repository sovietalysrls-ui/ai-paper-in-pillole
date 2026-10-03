"""Piccoli attrezzi condivisi: configurazione, prompt, file JSON, testo."""
import json
import os
import re
import string
import unicodedata
from pathlib import Path

import yaml

RADICE = Path(__file__).resolve().parent.parent


def _fondi(base, sopra):
    """Unisce due dizionari: i valori di "sopra" vincono, voce per voce."""
    for k, v in sopra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _fondi(base[k], v)
        else:
            base[k] = v
    return base


def _percorso(p):
    p = Path(os.path.expanduser(str(p)))
    return p if p.is_absolute() else (RADICE / p).resolve()


def carica_config(cloud=False):
    with open(RADICE / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    profilo = cfg.pop("profilo_cloud", {}) or {}
    if cloud:
        _fondi(cfg, profilo)
    cfg["cartella_base"] = _percorso(cfg["cartella_base"])
    cfg["archivio_git"] = _percorso(cfg["archivio_git"]) if cfg.get("archivio_git") else None
    carica_segreti()
    return cfg


def carica_segreti():
    """Legge segreti.env e mette i valori nelle variabili d'ambiente."""
    p = RADICE / "segreti.env"
    if not p.exists():
        return
    for riga in p.read_text(encoding="utf-8").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        k, v = riga.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def carica_lingua(codice):
    cartella = RADICE / "lingue" / codice
    with open(cartella / "lingua.yaml", encoding="utf-8") as f:
        dati = yaml.safe_load(f)
    with open(cartella / "vietate.yaml", encoding="utf-8") as f:
        dati["vietate"] = yaml.safe_load(f) or []
    pron = cartella / "pronuncia.yaml"
    dati["pronuncia_fissa"] = {}
    if pron.exists():
        with open(pron, encoding="utf-8") as f:
            dati["pronuncia_fissa"] = yaml.safe_load(f) or {}
    dati["codice"] = codice
    dati["cartella"] = cartella
    return dati


def prompt(lingua, nome, **valori):
    """Carica lingue/<x>/prompt/<nome>.md e riempie le $variabili.

    Il file ha due parti separate dalla riga ---UTENTE---:
    sopra le istruzioni di ruolo, sotto la richiesta vera.
    """
    testo = (lingua["cartella"] / "prompt" / f"{nome}.md").read_text(encoding="utf-8")
    sistema, _, utente = testo.partition("---UTENTE---")
    fondi = {k: (v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, indent=1))
             for k, v in valori.items()}
    return (string.Template(sistema.strip()).safe_substitute(fondi),
            string.Template(utente.strip()).safe_substitute(fondi))


def leggi_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def scrivi_json(p, dati):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
    tmp.replace(p)


def scrivi_testo(p, testo):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(testo.rstrip() + "\n", encoding="utf-8")
    tmp.replace(p)


def conta_parole(testo):
    return len(re.findall(r"\w+(?:['’]\w+)?", testo))


def slug(testo, n=40):
    t = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode()
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t[:n].rstrip("-") or "puntata"


def frasi(testo):
    return [f.strip() for f in re.split(r"(?<=[.!?])\s+", testo) if f.strip()]

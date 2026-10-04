#!/usr/bin/env python3
"""Prova delle voci: legge i primi turni di un dialogo archiviato, una voce per
richiesta, e misura l'altezza di ogni turno. Non pubblica niente.

  python prova_voci.py archivio/puntate/2026-10-04_052_graphforge/dialogo.txt 8
"""
import sys
import tempfile
from pathlib import Path

from kit import audio, voce
from kit.avvisi import Avanzamento
from kit.gemini import GeminiVoce
from kit.util import carica_config, carica_lingua, carica_segreti


def main():
    carica_segreti()
    file_dialogo, quanti = Path(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 8
    cfg = carica_config(cloud=True)
    L = carica_lingua("it")
    inverso = {v: k for k, v in L["conduttori"].items()}
    battute = []
    for riga in file_dialogo.read_text(encoding="utf-8").splitlines():
        if ":" in riga and not riga.startswith("["):
            nome, testo = riga.split(":", 1)
            if nome.strip() in inverso:
                battute.append((inverso[nome.strip()], testo.strip()))
    battute = battute[:quanti]
    cartella = Path(tempfile.mkdtemp())
    avanz = Avanzamento(["Prova voci"], cartella / "log.txt", telegram_attivo=False)
    motore = GeminiVoce(cfg["gemini_voce"], L, avanz)
    g, c = voce.genera(motore, battute, L, cartella, 14, avanz, "Prova voci", toni=cfg["gemini_voce"]["toni"])
    for p, (chi, t) in zip(g + c, battute):
        print(f"{p.name}: {audio.tono(p) or 0:.0f} Hz, {audio.durata(p):.1f} s")
    out = Path("prova_voci")
    out.mkdir(exist_ok=True)
    for p in g + c:
        p.replace(out / p.name)


if __name__ == "__main__":
    main()

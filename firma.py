#!/usr/bin/env python3
"""La frase finale della puntata ("AI Paper in Pillole è un progetto di Sovietaly SRLS").

È sempre uguale, quindi si registra una volta sola e si riusa ogni notte.

  python firma.py proponi     crea alcune versioni e le manda su Telegram
  python firma.py usa 2       la versione 2 diventa quella fissa (assets/firma_it.wav)
"""
import argparse
import copy
import shutil
import subprocess
import sys

from kit.avvisi import Avanzamento
from kit.gemini import GeminiVoce
from kit.util import RADICE, carica_config, carica_lingua, carica_segreti

CARTELLA = RADICE / "assets" / "proposte"

# (voce di Gemini, testo da leggere, stile)
STILE = ("Parla in italiano, con pronuncia italiana naturale, voce calda e sorridente, "
         "come la chiusura di un podcast italiano. Soviétaly ha l'accento sulla e.")
VERSIONI = [
    ("Aoede", "Ài Pèiper in Pìllole è un progetto di Soviétaly, esse erre elle esse.", STILE),
    ("Aoede", "Ài Pèiper in Pìllole è un progetto di Soviétaly, esse erre elle esse. Alla prossima!", STILE),
    ("Kore", "Ài Pèiper in Pìllole è un progetto di Soviétaly, esse erre elle esse.", STILE),
    ("Leda", "Ài Pèiper in Pìllole è un progetto di Soviétaly, esse erre elle esse.", STILE),
    ("Erinome", "Ài Pèiper in Pìllole è un progetto di Soviétaly, esse erre elle esse.", STILE),
]


def proponi(args):
    carica_segreti()
    CARTELLA.mkdir(parents=True, exist_ok=True)
    cfg = carica_config(cloud=True)
    lingua = carica_lingua("it")
    avanz = Avanzamento(["Frase finale"], CARTELLA / "firma.log", telegram_attivo=True,
                        intestazione="🎙 AI Paper in Pillole — versioni della frase finale")
    fatte = 0
    for i, (voce, testo, stile) in enumerate(VERSIONI, 1):
        avanz.inizia("Frase finale", f"versione {i} di {len(VERSIONI)}")
        c = copy.deepcopy(cfg["gemini_voce"])
        c["voci"]["ARIANNA"] = voce
        try:
            audio = GeminiVoce(c, lingua, avanz).blocco([("ARIANNA", testo)], stile=stile)
        except Exception as e:
            avanz.avviso(f"versione {i} non riuscita: {e}")
            continue
        wav = CARTELLA / f"firma_{i}.wav"
        wav.write_bytes(audio)
        mp3 = wav.with_suffix(".mp3")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-b:a", "128k", str(mp3)], check=True)
        avanz.manda_file(mp3, f"Versione {i}: voce {voce}", "audio")
        fatte += 1
    avanz.fatto("Frase finale", f"{fatte} versioni")
    avanz.fine(f"{fatte} versioni della frase finale pronte. Dimmi il numero che preferisci.")
    return 0 if fatte else 1


def usa(args):
    src = CARTELLA / f"firma_{args.numero}.wav"
    if not src.exists():
        print(f"Versione {args.numero} non trovata")
        return 1
    dest = RADICE / "assets" / "firma_it.wav"
    filtri = ("silenceremove=start_periods=1:start_threshold=-45dB,"
              "areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "44100",
                    "-af", filtri, str(dest)], check=True)
    print(f"Frase finale fissata: versione {args.numero} → {dest.relative_to(RADICE)}")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Frase finale della puntata")
    sub = ap.add_subparsers(dest="azione", required=True)
    sub.add_parser("proponi")
    u = sub.add_parser("usa")
    u.add_argument("numero", type=int)
    a = ap.parse_args()
    return {"proponi": proponi, "usa": usa}[a.azione](a)


if __name__ == "__main__":
    sys.exit(main())

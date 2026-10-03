#!/usr/bin/env python3
"""Sigla originale di AI Paper in Pillole, generata da zero.

Nessun campione e nessuna musica di terzi: ogni nota è calcolata dal
programma (corde pizzicate sintetiche più un basso morbido). Quindi la
musica è tua e non ha diritti da gestire.

Uso:
  python sigla.py              crea assets/sigla_apertura.wav e assets/sigla_chiusura.wav
  python sigla.py --varianti 6 crea 6 varianti in assets/varianti/ da ascoltare e scegliere

Si lancia una volta sola. La notte usa i file già pronti.
"""
import argparse
import wave
from pathlib import Path

import numpy as np

FREQ = 44100
RADICE = Path(__file__).resolve().parent


def nota(n):
    """Frequenza di una nota MIDI (69 = La 440 Hz)."""
    return 440.0 * 2 ** ((n - 69) / 12)


def corda(f, durata, luminosita=0.5, rng=None):
    """Corda pizzicata (algoritmo Karplus-Strong)."""
    rng = rng or np.random.default_rng(0)
    n = int(FREQ * durata)
    periodo = max(2, int(FREQ / f))
    buf = rng.uniform(-1, 1, periodo)
    out = np.empty(n)
    smorzamento = 0.996 - (1 - luminosita) * 0.004
    for i in range(n):
        out[i] = buf[i % periodo]
        buf[i % periodo] = smorzamento * 0.5 * (buf[i % periodo] + buf[(i + 1) % periodo])
    return out


def basso(f, durata):
    t = np.arange(int(FREQ * durata)) / FREQ
    inviluppo = np.minimum(t / 0.02, 1) * np.exp(-t * 2.2)
    return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * inviluppo


def mix(dest, src, inizio):
    i = int(inizio * FREQ)
    fine = min(len(dest), i + len(src))
    dest[i:fine] += src[: fine - i]


# Progressione LAm - FA - DO - SOL, arpeggiata, con un piccolo motivo in cima.
ACCORDI = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]
BASSI = [45, 41, 48, 43]


def componi(battute, bpm=104, seme=0, chiusura=False):
    rng = np.random.default_rng(seme)
    battito = 60 / bpm
    durata = battute * 4 * battito + 2.5
    out = np.zeros(int(FREQ * durata))
    ordine = list(range(len(ACCORDI)))
    if chiusura:
        ordine = [1, 2, 3, 0]          # chiude risolvendo su LAm
    motivo = rng.choice([0, 1, 2], size=8)
    for b in range(battute):
        acc = ACCORDI[ordine[b % 4]]
        t0 = b * 4 * battito
        mix(out, 0.45 * basso(nota(BASSI[ordine[b % 4]]), 4 * battito), t0)
        for k in range(8):                       # arpeggio a crome
            n = acc[[0, 1, 2, 1][k % 4]] + (12 if k >= 4 else 0)
            mix(out, 0.22 * corda(nota(n), 1.2, 0.55, rng), t0 + k * battito / 2)
        if b % 2 == 1 or chiusura:               # motivo in alto
            n = acc[motivo[b % 8]] + 24
            mix(out, 0.18 * corda(nota(n), 1.6, 0.8, rng), t0 + 2 * battito)
    if chiusura:                                  # accordo finale lungo
        t0 = battute * 4 * battito
        for n in ACCORDI[0]:
            mix(out, 0.2 * corda(nota(n + 12), 2.4, 0.5, rng), t0)
        mix(out, 0.4 * basso(nota(45), 2.4), t0)
    # dissolvenza finale e normalizzazione
    coda = int(FREQ * 1.2)
    out[-coda:] *= np.linspace(1, 0, coda)
    out /= max(1e-9, np.abs(out).max()) / 0.8
    return out


def salva(p, segnale):
    p.parent.mkdir(parents=True, exist_ok=True)
    dati = (np.clip(segnale, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FREQ)
        w.writeframes(dati)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--varianti", type=int, default=0)
    ap.add_argument("--seme", type=int, default=7)
    a = ap.parse_args()
    if a.varianti:
        for s in range(a.varianti):
            salva(RADICE / "assets" / "varianti" / f"apertura_{s}.wav", componi(2, seme=s))
            salva(RADICE / "assets" / "varianti" / f"chiusura_{s}.wav", componi(2, seme=s, chiusura=True))
        print(f"{a.varianti} varianti in assets/varianti/. Scegli il numero e lancia: python sigla.py --seme N")
        return
    salva(RADICE / "assets" / "sigla_apertura.wav", componi(2, seme=a.seme))
    salva(RADICE / "assets" / "sigla_chiusura.wav", componi(2, seme=a.seme, chiusura=True))
    print("Sigle create in assets/")


if __name__ == "__main__":
    main()

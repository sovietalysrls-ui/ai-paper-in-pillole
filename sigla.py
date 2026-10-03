#!/usr/bin/env python3
"""Sigla originale di AI Paper in Pillole, generata da zero.

Nessun campione e nessuna musica di terzi: ogni suono è calcolato dal
programma. Quindi la musica è tua e non ha diritti da gestire.

Carattere: allegro, luminoso. Tonalità maggiore, 126 battiti al minuto,
marimba, campanelli, basso che rimbalza, battito di mani e charleston.

Uso:
  python sigla.py              crea assets/sigla_apertura.wav e assets/sigla_chiusura.wav
  python sigla.py --varianti 6 crea 6 varianti in assets/varianti/ da ascoltare
  python sigla.py --seme 3     tiene la variante numero 3

Si lancia una volta sola. La notte usa i file già pronti.
"""
import argparse
import wave
from pathlib import Path

import numpy as np

FREQ = 44100
RADICE = Path(__file__).resolve().parent


def hz(n):
    """Frequenza di una nota MIDI (69 = La 440 Hz)."""
    return 440.0 * 2 ** ((n - 69) / 12)


def tempo(sec):
    return np.arange(int(FREQ * sec)) / FREQ


def marimba(f, dur=0.5):
    t = tempo(dur)
    attacco = np.minimum(t / 0.003, 1)
    return attacco * (np.sin(2 * np.pi * f * t) * np.exp(-t * 7)
                      + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t * 22))


def campanello(f, dur=1.0):
    t = tempo(dur)
    attacco = np.minimum(t / 0.002, 1)
    parziali = [(1, 1.0, 3.0), (2.76, 0.45, 6.0), (5.40, 0.25, 9.0), (8.93, 0.12, 14.0)]
    return attacco * sum(a * np.sin(2 * np.pi * f * k * t) * np.exp(-t * d) for k, a, d in parziali)


def basso(f, dur=0.3):
    t = tempo(dur)
    onda = np.tanh(2.5 * np.sin(2 * np.pi * f * t))          # un po' "spesso", rimbalzante
    return onda * np.minimum(t / 0.004, 1) * np.exp(-t * 9)


def cassa(dur=0.25):
    t = tempo(dur)
    f = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / FREQ) * np.exp(-t * 14)


def charleston(rng, dur=0.05):
    n = rng.uniform(-1, 1, int(FREQ * dur))
    n = np.diff(n, prepend=0)                                  # toglie i bassi: suono metallico
    return n * np.exp(-tempo(dur) * 80)


def mani(rng, dur=0.14):
    t = tempo(dur)
    n = rng.uniform(-1, 1, len(t))
    n = n - np.convolve(n, np.ones(6) / 6, mode="same")       # banda media, "schiocco"
    colpi = sum(np.exp(-np.maximum(t - k * 0.011, 0) * 60) * (t >= k * 0.011) for k in range(3))
    return n * colpi / 3


def metti(dest, src, inizio, vol=1.0):
    i = int(inizio * FREQ)
    if i >= len(dest):
        return
    fine = min(len(dest), i + len(src))
    dest[i:fine] += vol * src[: fine - i]


# DO - SOL - LAm - FA (I - V - vi - IV): la progressione allegra per eccellenza.
ACCORDI = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
BASSI = [36, 43, 45, 41]
SCALA = [72, 74, 76, 79, 81, 84]          # pentatonica di DO, in alto: sempre "solare"


def componi(seme=0, chiusura=False, bpm=126):
    rng = np.random.default_rng(seme)
    b = 60 / bpm                           # durata di un battito
    battute = 2
    durata = battute * 4 * b + 1.4
    out = np.zeros(int(FREQ * durata))

    # motivo della melodia: 8 note su ritmo sincopato, scelto dal "seme"
    ritmo = [0, 0.75, 1.5, 2, 2.5, 3, 3.5, 3.75]
    motivo = [SCALA[i] for i in rng.integers(0, len(SCALA), 8)]
    motivo[-1] = 84 if chiusura else motivo[-1]

    ordine = [0, 1, 2, 3] if not chiusura else [3, 1, 0, 0]
    for m in range(battute):
        t0 = m * 4 * b
        for meta in range(2):              # due accordi per battuta
            acc = ACCORDI[ordine[m * 2 + meta]]
            tb = t0 + meta * 2 * b
            # marimba: accordo arpeggiato in sedicesimi
            for k in range(8):
                nota = acc[[0, 1, 2, 1][k % 4]] + 12
                metti(out, marimba(hz(nota)), tb + k * b / 4, 0.16)
            # basso che rimbalza: battere e controtempo
            for s, ottava in ((0, 0), (0.5, 12), (1, 0), (1.5, 12)):
                metti(out, basso(hz(BASSI[ordine[m * 2 + meta]] + ottava)), tb + s * b, 0.22)
        # batteria leggera
        for k in range(4):
            metti(out, cassa(), t0 + k * b, 0.35)
            if k in (1, 3):
                metti(out, mani(rng), t0 + k * b, 0.35)
        for k in range(8):
            metti(out, charleston(rng), t0 + k * b / 2 + b / 4, 0.10)
        # melodia ai campanelli, nella seconda battuta (o in entrambe in chiusura)
        if m == 1 or chiusura:
            for r, nota in zip(ritmo, motivo):
                metti(out, campanello(hz(nota)), t0 + r * b, 0.20)

    # colpo finale: accordo di DO pieno + piatto finto
    tf = battute * 4 * b
    for nota in (60, 64, 67, 72):
        metti(out, campanello(hz(nota + 12), 2.0), tf, 0.12)
        metti(out, marimba(hz(nota), 1.2), tf, 0.15)
    metti(out, basso(hz(36), 0.8), tf, 0.3)
    metti(out, cassa(), tf, 0.4)
    metti(out, mani(rng), tf, 0.3)

    coda = int(FREQ * 0.6)
    out[-coda:] *= np.linspace(1, 0, coda)
    out /= max(1e-9, np.abs(out).max()) / 0.85
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
    ap.add_argument("--seme", type=int, default=1)
    a = ap.parse_args()
    if a.varianti:
        for s in range(a.varianti):
            salva(RADICE / "assets" / "varianti" / f"apertura_{s}.wav", componi(seme=s))
            salva(RADICE / "assets" / "varianti" / f"chiusura_{s}.wav", componi(seme=s, chiusura=True))
        print(f"{a.varianti} varianti in assets/varianti/. Scegli il numero e lancia: python sigla.py --seme N")
        return
    salva(RADICE / "assets" / "sigla_apertura.wav", componi(seme=a.seme))
    salva(RADICE / "assets" / "sigla_chiusura.wav", componi(seme=a.seme, chiusura=True))
    print("Sigle create in assets/")


if __name__ == "__main__":
    main()

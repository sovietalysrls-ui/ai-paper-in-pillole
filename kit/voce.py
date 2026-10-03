"""Passo 7: la voce. Divide il dialogo in blocchi e li fa leggere.

Il primo blocco è il gancio (le battute prima della presentazione):
così il montaggio può mettere la sigla subito dopo.
Ogni blocco viene salvato appena pronto: se la notte si interrompe,
alla ripartenza si rifanno solo i blocchi mancanti.
"""
import io
import wave
from pathlib import Path

import numpy as np

from .util import conta_parole


def dividi(battute, lingua, per_blocco):
    nome = lingua["nome_podcast"].lower()
    idx = next((i for i, (_, b) in enumerate(battute) if nome in b.lower()), 0)
    gancio = [battute[:idx]] if idx else []
    resto = battute[idx:]
    corpo = [resto[i:i + per_blocco] for i in range(0, len(resto), per_blocco)]
    # evita un ultimo blocco minuscolo: lo unisce al precedente
    if len(corpo) > 1 and len(corpo[-1]) < 3:
        corpo[-2] += corpo.pop()
    return gancio, corpo


def genera(motore, battute, lingua, cartella, per_blocco, avanz, passo):
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    gancio, corpo = dividi(battute, lingua, per_blocco)
    tutti = [("gancio", b) for b in gancio] + [("corpo", b) for b in corpo]
    file_g, file_c = [], []
    for n, (tipo, blocco) in enumerate(tutti, 1):
        p = cartella / f"blocco_{n:02d}_{tipo}.wav"
        if not p.exists() or p.stat().st_size < 1000:
            avanz.inizia(passo, f"blocco {n} di {len(tutti)} ({len(blocco)} battute)")
            p.write_bytes(motore.blocco(blocco))
        (file_g if tipo == "gancio" else file_c).append(p)
    return file_g, file_c


class VoceFinta:
    """Per i collaudi: un tono diverso per ogni conduttore, lungo quanto la battuta."""

    richieste = 0

    def blocco(self, battute):
        freq = 24000
        pezzi = []
        for chi, testo in battute:
            sec = max(0.6, conta_parole(testo) / 2.6)
            t = np.arange(int(freq * sec)) / freq
            f = 180 if chi == "CARLO" else 260
            pezzi += [0.2 * np.sin(2 * np.pi * f * t) * np.minimum(1, t * 20), np.zeros(int(freq * 0.3))]
        dati = (np.concatenate(pezzi) * 32767).astype("<i2").tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(freq)
            w.writeframes(dati)
        return buf.getvalue()

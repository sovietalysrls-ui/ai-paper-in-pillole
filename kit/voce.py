"""Passo 7: la voce. Divide il dialogo in blocchi e li fa leggere.

Il primo blocco è l'apertura: gancio e presentazione. Il montaggio
mette la sigla subito dopo, poi parte il paper.
Ogni blocco viene salvato appena pronto: se la notte si interrompe,
alla ripartenza si rifanno solo i blocchi mancanti.
"""
import io
import wave
from pathlib import Path

import numpy as np

from .util import conta_parole


def fine_presentazione(battute, lingua):
    """Indice dell'ultima battuta della presentazione.

    La presentazione inizia alla prima battuta con il nome del podcast.
    Finisce quando si è presentato anche il secondo conduttore
    ("E io sono Carlo"), al massimo due battute dopo.
    """
    nome = lingua["nome_podcast"].lower()
    inizio = next((i for i, (_, b) in enumerate(battute) if nome in b.lower()), None)
    if inizio is None:
        return -1
    nomi = [v.lower() for v in lingua["conduttori"].values()]
    for i in range(inizio, min(inizio + 3, len(battute))):
        b = battute[i][1].lower()
        presentati = sum(1 for n in nomi for j in range(inizio, i + 1) if n in battute[j][1].lower())
        if presentati >= len(nomi) and i > inizio:
            return i
        if i == inizio and all(n in b for n in nomi):
            return i
    return min(inizio + 1, len(battute) - 1)


def dividi(battute, lingua, per_blocco):
    fine = fine_presentazione(battute, lingua)
    apertura = [battute[:fine + 1]] if fine >= 0 else []
    resto = battute[fine + 1:]
    corpo = [resto[i:i + per_blocco] for i in range(0, len(resto), per_blocco)]
    # evita un ultimo blocco minuscolo: lo unisce al precedente
    if len(corpo) > 1 and len(corpo[-1]) < 3:
        corpo[-2] += corpo.pop()
    return apertura, corpo


def genera_firma(motore, lingua, cartella, avanz, passo):
    """La frase finale ("AI Paper in Pillole è un progetto di...")."""
    ff = lingua.get("frase_finale")
    if not ff:
        return None
    p = Path(cartella) / "blocco_99_firma.wav"
    if not p.exists() or p.stat().st_size < 1000:
        avanz.inizia(passo, "frase finale")
        p.write_bytes(motore.blocco([(ff.get("chi", "ARIANNA"), ff.get("voce") or ff["testo"])]))
    return p


def genera(motore, battute, lingua, cartella, per_blocco, avanz, passo):
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    apertura, corpo = dividi(battute, lingua, per_blocco)
    tutti = [("apertura", b) for b in apertura] + [("corpo", b) for b in corpo]
    file_g, file_c = [], []
    for n, (tipo, blocco) in enumerate(tutti, 1):
        p = cartella / f"blocco_{n:02d}_{tipo}.wav"
        if not p.exists() or p.stat().st_size < 1000:
            avanz.inizia(passo, f"blocco {n} di {len(tutti)} ({len(blocco)} battute)")
            p.write_bytes(motore.blocco(blocco))
        (file_g if tipo == "apertura" else file_c).append(p)
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

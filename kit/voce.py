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
    # La frase è sempre uguale: se è stata scelta una registrazione fissa
    # (python firma.py usa N), si usa quella e non si consuma quota.
    if ff.get("file"):
        from kit.util import RADICE
        fisso = RADICE / ff["file"]
        if fisso.exists():
            return fisso
    p = Path(cartella) / "blocco_99_firma.wav"
    if not p.exists() or p.stat().st_size < 1000:
        avanz.inizia(passo, "frase finale")
        try:
            dati = motore.blocco([(ff.get("chi", "ARIANNA"), ff.get("voce") or ff["testo"])], stile=ff.get("stile"))
        except TypeError:          # motori senza stile (voce finta)
            dati = motore.blocco([(ff.get("chi", "ARIANNA"), ff.get("voce") or ff["testo"])])
        p.write_bytes(dati)
    return p


class ErroreVoci(RuntimeError):
    pass


def turni(battute):
    """Raggruppa le battute di fila della stessa persona: ogni turno ha una sola voce."""
    out = []
    for chi, testo in battute:
        if out and out[-1][0][0] == chi:
            out[-1].append((chi, testo))
        else:
            out.append([(chi, testo)])
    return out


def genera(motore, battute, lingua, cartella, per_blocco, avanz, passo, toni=None):
    """Fa leggere il dialogo un turno alla volta: in ogni richiesta c'è una sola
    persona e una sola voce, così le voci non possono essere scambiate.

    toni: {"CARLO": "basso", "ARIANNA": "alto"}. Se c'è, dopo la lettura si misura
    l'altezza di ogni turno; un turno con la voce sbagliata viene rifatto, e se
    resta sbagliato la puntata si ferma con un errore (meglio nessun audio che
    voci scambiate).
    """
    cartella = Path(cartella)
    cartella.mkdir(parents=True, exist_ok=True)
    apertura, corpo = dividi(battute, lingua, per_blocco)
    lista = ([("apertura", t) for b in apertura for t in turni(b)] +
             [("corpo", t) for b in corpo for t in turni(b)])
    file_g, file_c, chi_file = [], [], []
    for n, (tipo, turno) in enumerate(lista, 1):
        chi = turno[0][0]
        p = cartella / f"turno_{n:03d}_{tipo}_{chi.lower()}.wav"
        if not p.exists() or p.stat().st_size < 1000:
            avanz.inizia(passo, f"turno {n} di {len(lista)} ({lingua['conduttori'][chi]})")
            p.write_bytes(motore.blocco(turno))
        (file_g if tipo == "apertura" else file_c).append(p)
        chi_file.append((chi, p, turno))
    if toni:
        controlla_voci(motore, chi_file, toni, lingua, avanz, passo)
    return file_g, file_c


def controlla_voci(motore, chi_file, toni, lingua, avanz, passo):
    from . import audio
    misure = {p: audio.tono(p) for _, p, _ in chi_file}
    bassi = [misure[p] for chi, p, _ in chi_file if toni.get(chi) == "basso" and misure[p]]
    alti = [misure[p] for chi, p, _ in chi_file if toni.get(chi) == "alto" and misure[p]]
    if not bassi or not alti:
        avanz.avviso("controllo voci: non sono riuscito a misurare le voci")
        return
    m_b, m_a = float(np.median(bassi)), float(np.median(alti))
    if m_a - m_b < 20:
        raise ErroreVoci(f"le due voci hanno quasi la stessa altezza ({m_b:.0f} e {m_a:.0f} Hz) "
                         "oppure sono scambiate: controlla le voci in config.yaml")
    soglia = (m_b + m_a) / 2

    def sbagliata(chi, f):
        if f is None:
            return False
        return (toni.get(chi) == "basso" and f > soglia + 10) or (toni.get(chi) == "alto" and f < soglia - 10)

    for chi, p, turno in chi_file:
        f = misure[p]
        tentativi = 0
        while sbagliata(chi, f) and tentativi < 2:
            tentativi += 1
            avanz.avviso(f"voce sospetta per {lingua['conduttori'][chi]} ({f:.0f} Hz, attesa "
                         f"{'sotto' if toni[chi] == 'basso' else 'sopra'} {soglia:.0f} Hz): rifaccio il turno")
            avanz.inizia(passo, f"rifaccio {p.name}")
            p.write_bytes(motore.blocco(turno))
            f = audio.tono(p)
        if sbagliata(chi, f):
            raise ErroreVoci(f"{p.name}: la voce di {lingua['conduttori'][chi]} risulta sbagliata anche dopo "
                             f"2 tentativi ({f:.0f} Hz). Puntata fermata per non pubblicare voci scambiate.")
    avanz.scrivi(f"   controllo voci: {lingua['conduttori'].get('CARLO', 'CARLO')} ~{m_b:.0f} Hz, "
                 f"{lingua['conduttori'].get('ARIANNA', 'ARIANNA')} ~{m_a:.0f} Hz, tutto in ordine")


class VoceFinta:
    """Per i collaudi: un tono diverso per ogni conduttore, lungo quanto la battuta."""

    richieste = 0

    def blocco(self, battute, stile=None):
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

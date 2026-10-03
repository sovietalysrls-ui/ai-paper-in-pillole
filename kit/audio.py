"""Montaggio audio: voci, pause, sigle, volume, wav e mp3.

ffmpeg è il programma standard per convertire e trattare l'audio.
Qui serve per tre cose: portare tutto allo stesso formato, togliere
i silenzi ai bordi dei blocchi di voce, livellare il volume finale.
Il mescolamento (voce sopra la sigla) lo fa numpy, una libreria di
calcolo: più semplice da controllare di un filtro ffmpeg.
"""
import subprocess
import wave
from pathlib import Path

import numpy as np

FREQ = 44100


def _ffmpeg(*args):
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg: {r.stderr.strip()[:500]}")


def durata(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def carica(p, togli_silenzi=False):
    """Legge un file audio qualsiasi come array mono a 44,1 kHz."""
    tmp = Path(str(p) + ".norm.wav")
    filtri = ["aresample=44100"]
    if togli_silenzi:
        # toglie il silenzio all'inizio e (girando l'audio) alla fine
        filtri += ["silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05",
                   "areverse",
                   "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05",
                   "areverse"]
    _ffmpeg("-i", str(p), "-ac", "1", "-af", ",".join(filtri), "-c:a", "pcm_s16le", str(tmp))
    with wave.open(str(tmp)) as w:
        dati = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    tmp.unlink()
    return dati


def _salva(p, segnale):
    dati = (np.clip(segnale, -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(FREQ)
        w.writeframes(dati)


def silenzio(sec):
    return np.zeros(int(FREQ * sec), dtype=np.float32)


def monta(gancio, corpo, sigla_ap, sigla_ch, uscita_wav, uscita_mp3, cfg_a):
    """gancio: blocchi di voce dell'apertura (gancio + presentazione);
    corpo: blocchi del resto della puntata.

    Schema: gancio e presentazione → sigla → paper e chiusura → sigla finale.
    Con sovrapposizione_sigla > 0 la sigla sfuma sotto la voce che segue;
    con 0 (predefinito) la sigla suona intera, da sola.
    """
    pausa = cfg_a.get("pausa_tra_blocchi", 0.35)

    def unisci(files):
        pezzi = []
        for f in files:
            pezzi += [carica(f, togli_silenzi=True), silenzio(pausa)]
        return np.concatenate(pezzi[:-1]) if pezzi else np.zeros(0, np.float32)

    voce_g, voce_c = unisci(gancio), unisci(corpo)
    s_ap = carica(sigla_ap) * cfg_a.get("volume_sigla", 0.5) if sigla_ap and Path(sigla_ap).exists() else np.zeros(0)
    s_ch = carica(sigla_ch) * cfg_a.get("volume_sigla", 0.5) if sigla_ch and Path(sigla_ch).exists() else np.zeros(0)

    sovrapposizione = cfg_a.get("sovrapposizione_sigla", 0)   # secondi di sigla sotto la voce
    t_sigla = len(voce_g) + int(FREQ * 0.5) if len(voce_g) else 0
    if len(s_ap):
        t_corpo = t_sigla + max(len(s_ap) - int(FREQ * sovrapposizione), 0)
        if sovrapposizione <= 0:
            t_corpo += int(FREQ * 0.4)          # respiro dopo la sigla
    else:
        t_corpo = t_sigla
    t_chius = t_corpo + len(voce_c) + int(FREQ * 0.6)
    totale = max(t_chius + len(s_ch), t_corpo + len(voce_c)) + int(FREQ * 0.5)
    mix = np.zeros(totale, np.float32)

    mix[:len(voce_g)] += voce_g
    if len(s_ap):
        sig = s_ap.copy()
        if sovrapposizione > 0:
            # sotto la voce la sigla scende di volume e sfuma
            inizio_sfumo = max(len(sig) - int(FREQ * sovrapposizione), 0)
            sig[inizio_sfumo:] *= np.linspace(0.6, 0.0, len(sig) - inizio_sfumo)
        mix[t_sigla:t_sigla + len(sig)] += sig
    mix[t_corpo:t_corpo + len(voce_c)] += voce_c
    if len(s_ch):
        mix[t_chius:t_chius + len(s_ch)] += s_ch

    grezzo = Path(uscita_wav).with_suffix(".grezzo.wav")
    _salva(grezzo, mix)
    # Livellamento del volume allo standard dei podcast (-16 LUFS).
    filtro = f"loudnorm=I={cfg_a.get('lufs', -16)}:TP=-1.5:LRA=11"
    _ffmpeg("-i", str(grezzo), "-af", filtro, "-ar", str(FREQ), "-ac", "1",
            "-c:a", "pcm_s16le", str(uscita_wav))
    _ffmpeg("-i", str(uscita_wav), "-c:a", "libmp3lame", "-b:a", cfg_a.get("mp3_bitrate", "128k"),
            str(uscita_mp3))
    grezzo.unlink()
    return {"durata": durata(uscita_wav), "voce": (len(voce_g) + len(voce_c)) / FREQ}

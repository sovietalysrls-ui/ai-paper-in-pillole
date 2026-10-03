#!/usr/bin/env python3
"""Sigla di AI Paper in Pillole con Lyria, il modello musicale di Google.

Passo 1, proposte:
  python musica.py proponi            crea 6 proposte in stili diversi
  python musica.py proponi --stile "funky con basso slap"   proposte in uno stile scelto da te
Le proposte finiscono in assets/proposte/ e, se il bot è configurato,
arrivano su Telegram per essere ascoltate dal telefono.

Passo 2, scelta:
  python musica.py usa 3              ricava apertura e chiusura dalla proposta 3

Oppure, se hai già due file tuoi (per esempio generati in AI Studio):
  python musica.py imposta intro.mp3 outro.mp3
toglie i silenzi ai bordi, sfuma la fine e li salva come sigle.

L'apertura è l'inizio del brano (con sfumatura finale), la chiusura è
la parte finale. Le durate si cambiano con --apertura e --chiusura.

Nota: l'audio di Lyria contiene SynthID, una filigrana digitale non
udibile che indica che il brano è generato da un'AI.
"""
import argparse
import subprocess
import sys
from pathlib import Path

from kit.avvisi import Avanzamento
from kit.gemini import GeminiMusica, estensione_audio
from kit.util import RADICE, carica_segreti

BASE = ("Instrumental podcast intro jingle, no vocals. Upbeat, catchy and bright, "
        "with a clear memorable melodic hook from the very first second. "
        "Modern, professional, radio-ready mix. Builds quickly, then ends with a clean resolving hit. ")

STILI = [
    "Modern tech podcast style: punchy electronic drums, warm synth bass, plucky synth lead, around 120 BPM.",
    "Feel-good indie pop: clean electric guitar riff, claps, bouncy bass, tambourine, around 118 BPM.",
    "Funky groove: slap bass, brass stabs, wah guitar, tight drums, around 110 BPM.",
    "Lo-fi hip hop but cheerful: dusty drums, Rhodes piano chords, vinyl crackle, playful melody, around 90 BPM.",
    "Playful acoustic: ukulele, glockenspiel, whistling-like synth, handclaps, sunny mood, around 115 BPM.",
    "Synthwave optimistic: retro 80s synths, gated drums, arpeggiator, shiny lead, around 112 BPM.",
]

CARTELLA = RADICE / "assets" / "proposte"


def proponi(args):
    carica_segreti()
    CARTELLA.mkdir(parents=True, exist_ok=True)
    avanz = Avanzamento(["Proposte di sigla"], CARTELLA / "proposte.log", telegram_attivo=True,
                        intestazione="🎵 AI Paper in Pillole — proposte di sigla")
    lyria = GeminiMusica(args.modello, avanz)
    stili = [args.stile] * args.quante if args.stile else STILI[: args.quante]
    fatte = 0
    for i, stile in enumerate(stili, 1):
        avanz.inizia("Proposte di sigla", f"proposta {i} di {len(stili)}")
        try:
            audio = lyria.genera(BASE + stile)
        except Exception as e:
            avanz.avviso(f"proposta {i} non riuscita: {e}")
            continue
        p = CARTELLA / f"proposta_{i}{estensione_audio(audio)}"
        p.write_bytes(audio)
        mp3 = p.with_suffix(".mp3")
        if p.suffix != ".mp3":
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(p), "-b:a", "192k", str(mp3)], check=True)
        (CARTELLA / f"proposta_{i}.txt").write_text(BASE + stile + "\n", encoding="utf-8")
        avanz.manda_file(mp3, f"Proposta {i}: {stile}", "audio")
        fatte += 1
    avanz.fatto("Proposte di sigla", f"{fatte} proposte")
    avanz.fine(f"{fatte} proposte di sigla pronte. Rispondi con il numero che preferisci.")
    return 0 if fatte else 1


def usa(args):
    sorgenti = [p for p in CARTELLA.glob(f"proposta_{args.numero}.*") if p.suffix in (".wav", ".mp3", ".flac", ".ogg")]
    if not sorgenti:
        print(f"Proposta {args.numero} non trovata in {CARTELLA}")
        return 1
    src = sorted(sorgenti, key=lambda p: p.suffix != ".wav")[0]
    durata = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout)
    ap, ch = args.apertura, min(args.chiusura, durata)
    dest = RADICE / "assets"
    # apertura: i primi secondi, con sfumatura nell'ultimo secondo e mezzo
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-t", str(ap), "-ac", "1", "-ar", "44100",
                    "-af", f"afade=t=out:st={ap - 1.5}:d=1.5", str(dest / "sigla_apertura.wav")], check=True)
    # chiusura: gli ultimi secondi del brano, con breve entrata in dissolvenza
    inizio = max(durata - ch, 0)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(inizio), "-i", str(src), "-ac", "1", "-ar", "44100",
                    "-af", f"afade=t=in:d=0.8,afade=t=out:st={max(ch - 1.5, 0)}:d=1.5",
                    str(dest / "sigla_chiusura.wav")], check=True)
    print(f"Sigla impostata dalla proposta {args.numero}: apertura {ap}s, chiusura {ch:.1f}s")
    return 0


def _prepara(src, dest, max_sec):
    """Mono 44,1 kHz, silenzi ai bordi tolti, al massimo max_sec, sfumatura finale."""
    tmp = dest.with_suffix(".tmp.wav")
    filtri = ("silenceremove=start_periods=1:start_threshold=-50dB,"
              "areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", "44100",
                    "-af", filtri, "-t", str(max_sec), str(tmp)], check=True)
    durata = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                   "-of", "csv=p=0", str(tmp)], capture_output=True, text=True).stdout)
    sfumo = min(1.2, durata / 4)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
                    "-af", f"afade=t=out:st={durata - sfumo:.2f}:d={sfumo:.2f}", str(dest)], check=True)
    tmp.unlink()
    return durata


def imposta(args):
    dest = RADICE / "assets"
    d1 = _prepara(Path(args.intro), dest / "sigla_apertura.wav", args.massimo)
    print(f"Apertura: {d1:.1f} secondi")
    if args.outro:
        d2 = _prepara(Path(args.outro), dest / "sigla_chiusura.wav", args.massimo)
        print(f"Chiusura: {d2:.1f} secondi")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Sigla con Lyria")
    sub = ap.add_subparsers(dest="azione", required=True)
    p = sub.add_parser("proponi")
    p.add_argument("--quante", type=int, default=6)
    p.add_argument("--stile", default="")
    p.add_argument("--modello", default="lyria-3-clip-preview")
    u = sub.add_parser("usa")
    u.add_argument("numero", type=int)
    u.add_argument("--apertura", type=float, default=7.0)
    u.add_argument("--chiusura", type=float, default=8.0)
    i = sub.add_parser("imposta")
    i.add_argument("intro")
    i.add_argument("outro", nargs="?")
    i.add_argument("--massimo", type=float, default=20.0)
    a = ap.parse_args()
    return {"proponi": proponi, "usa": usa, "imposta": imposta}[a.azione](a)


if __name__ == "__main__":
    sys.exit(main())

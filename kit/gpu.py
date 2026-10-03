"""Contatore della memoria video.

Ogni 2 secondi chiede a nvidia-smi quanta memoria della scheda video
è occupata e tiene il valore più alto. Serve sul PC di sviluppo
(16 GB) per capire se il lavoro starebbe nella 1070 (8 GB).
"""
import shutil
import subprocess
import threading


class ContatoreVRAM:
    def __init__(self, intervallo=2.0):
        self.picco = 0
        self.totale = 0
        self.nome = ""
        self.attivo = shutil.which("nvidia-smi") is not None
        self._stop = threading.Event()
        self._t = None
        self.picchi_per_fase = {}
        self.fase = "avvio"
        self.intervallo = intervallo

    def _leggi(self):
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total,name",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        if not out:
            return None
        usata, totale, nome = [x.strip() for x in out[0].split(",", 2)]
        return int(usata), int(totale), nome

    def _giro(self):
        while not self._stop.is_set():
            try:
                v = self._leggi()
                if v:
                    usata, self.totale, self.nome = v
                    self.picco = max(self.picco, usata)
                    self.picchi_per_fase[self.fase] = max(self.picchi_per_fase.get(self.fase, 0), usata)
            except Exception:
                pass
            self._stop.wait(self.intervallo)

    def avvia(self):
        if self.attivo:
            self._t = threading.Thread(target=self._giro, daemon=True)
            self._t.start()
        return self

    def ferma(self):
        self._stop.set()
        if self._t:
            self._t.join(timeout=5)

    def rapporto(self, limite_mb):
        if not self.attivo:
            return "memoria video non misurata (nvidia-smi assente)", False
        fasi = ", ".join(f"{f} {v / 1024:.1f} GB" for f, v in self.picchi_per_fase.items() if v)
        sfora = self.picco > limite_mb
        testo = (f"Picco memoria video: {self.picco / 1024:.1f} GB su {self.totale / 1024:.0f} GB "
                 f"({self.nome}). Per fase: {fasi}. Limite 1070: {limite_mb / 1024:.1f} GB")
        return testo, sfora

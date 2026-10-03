"""Avanzamento a schermo, file di registro e messaggi Telegram.

A schermo: una riga per passo, con l'ora, e una riga "viva" che si
aggiorna mentre il modello scrive.
Su Telegram: un messaggio che si aggiorna a ogni passo, più un
messaggio nuovo (con notifica) alla fine o in caso di errore.
"""
import datetime as dt
import os
import sys
import time
import traceback

import requests

SIMBOLI = {"attesa": "▫️", "corso": "⏳", "ok": "✅", "errore": "❌", "avviso": "⚠️", "saltato": "↪️"}


class Avanzamento:
    def __init__(self, passi, file_log, telegram_attivo=True, intestazione=""):
        self.passi = list(passi)
        self.stati = {p: ("attesa", "") for p in self.passi}
        self.log = open(file_log, "a", encoding="utf-8")
        self.intestazione = intestazione
        self.token = os.environ.get("TELEGRAM_TOKEN", "").strip()
        self.chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        self.tg = telegram_attivo and bool(self.token and self.chat)
        self.msg_id = None
        self._ultimo_tg = 0
        self._riga_viva = False
        self.avvisi = []
        self.corrente = None
        self.inizio = time.time()
        self.scrivi(f"===== Avvio {dt.datetime.now():%Y-%m-%d %H:%M} =====")
        if telegram_attivo and not self.tg:
            self.scrivi("Telegram non configurato (segreti.env): avvisi solo a schermo.")
        self._aggiorna_tg(forza=True)

    # ---------------- schermo e log ----------------
    def _chiudi_riga_viva(self):
        if self._riga_viva:
            sys.stdout.write("\n")
            self._riga_viva = False

    def scrivi(self, testo):
        self._chiudi_riga_viva()
        riga = f"[{dt.datetime.now():%H:%M:%S}] {testo}"
        print(riga, flush=True)
        self.log.write(riga + "\n")
        self.log.flush()

    def vivo(self, testo):
        """Riga che si sovrascrive: per il modello che sta scrivendo."""
        sys.stdout.write("\r    " + testo[:110].ljust(110))
        sys.stdout.flush()
        self._riga_viva = True

    # ---------------- passi ----------------
    def inizia(self, passo, nota=""):
        self.corrente = passo
        self.stati[passo] = ("corso", nota)
        self.scrivi(f"▶ {passo}" + (f" — {nota}" if nota else ""))
        self._aggiorna_tg()

    def fatto(self, passo, nota=""):
        self.stati[passo] = ("ok", nota)
        self.scrivi(f"✔ {passo}" + (f" — {nota}" if nota else ""))
        self._aggiorna_tg()

    def saltato(self, passo, nota="già fatto"):
        self.stati[passo] = ("saltato", nota)
        self.scrivi(f"↪ {passo} — {nota}")
        self._aggiorna_tg()

    def avviso(self, testo):
        self.avvisi.append(testo)
        self.scrivi(f"⚠ {testo}")

    def errore(self, passo, exc):
        if self.corrente and self.stati.get(self.corrente, ("",))[0] == "corso":
            passo = self.corrente
        self.stati[passo] = ("errore", str(exc)[:200])
        self.scrivi(f"✖ {passo} — ERRORE: {exc}")
        self.log.write(traceback.format_exc() + "\n")
        self.log.flush()
        self._aggiorna_tg(forza=True)
        self.manda(f"❌ AI Paper in Pillole: errore al passo «{passo}».\n\n{str(exc)[:900]}\n\n"
                   f"Dettagli nel file registro.log della cartella OGGI. "
                   f"Rilanciando il programma riparte da questo passo.")

    def fine(self, riepilogo):
        minuti = (time.time() - self.inizio) / 60
        self.scrivi(f"===== Finito in {minuti:.0f} minuti =====")
        self._aggiorna_tg(forza=True)
        testo = f"✅ {riepilogo}\n⏱ {minuti:.0f} minuti"
        if self.avvisi:
            testo += "\n\nDa controllare:\n" + "\n".join(f"• {a}" for a in self.avvisi[:10])
        self.manda(testo)

    # ---------------- Telegram ----------------
    def _testo_tg(self):
        righe = [self.intestazione or "AI Paper in Pillole", ""]
        for i, p in enumerate(self.passi, 1):
            stato, nota = self.stati[p]
            righe.append(f"{SIMBOLI[stato]} {i}. {p}" + (f" — {nota}" if nota else ""))
        return "\n".join(righe)[:4000]

    def _aggiorna_tg(self, forza=False):
        if not self.tg:
            return
        # Telegram limita i messaggi: al massimo un aggiornamento ogni 3 secondi.
        if not forza and time.time() - self._ultimo_tg < 3:
            return
        self._ultimo_tg = time.time()
        base = f"https://api.telegram.org/bot{self.token}"
        try:
            if self.msg_id is None:
                r = requests.post(f"{base}/sendMessage", timeout=15,
                                  json={"chat_id": self.chat, "text": self._testo_tg(),
                                        "disable_notification": True})
                self.msg_id = r.json().get("result", {}).get("message_id")
            else:
                requests.post(f"{base}/editMessageText", timeout=15,
                              json={"chat_id": self.chat, "message_id": self.msg_id,
                                    "text": self._testo_tg()})
        except requests.RequestException as e:
            self.log.write(f"Telegram non raggiungibile: {e}\n")

    def manda_file(self, percorso, didascalia="", come="documento"):
        """Manda un file nella chat: come="audio" lo rende ascoltabile nel telefono."""
        if not self.tg:
            return False
        metodo, campo = {"audio": ("sendAudio", "audio"), "foto": ("sendPhoto", "photo")}.get(
            come, ("sendDocument", "document"))
        try:
            with open(percorso, "rb") as f:
                r = requests.post(f"https://api.telegram.org/bot{self.token}/{metodo}", timeout=300,
                                  data={"chat_id": self.chat, "caption": didascalia[:1000]},
                                  files={campo: f})
            if r.status_code != 200:
                self.log.write(f"Telegram ha rifiutato {percorso}: {r.text[:200]}\n")
                return False
            return True
        except (requests.RequestException, OSError) as e:
            self.log.write(f"Telegram non raggiungibile: {e}\n")
            return False

    def manda(self, testo):
        if not self.tg:
            return
        try:
            requests.post(f"https://api.telegram.org/bot{self.token}/sendMessage", timeout=15,
                          json={"chat_id": self.chat, "text": testo[:4000]})
        except requests.RequestException as e:
            self.log.write(f"Telegram non raggiungibile: {e}\n")

"""Collegamento a Gemini (Google), per testo e voce.

Due chiavi:
  GEMINI_API_KEY_GRATIS     la chiave gratuita, usata per prima
  GEMINI_API_KEY_PAGAMENTO  la chiave a pagamento, usata solo quando la
                            gratuita ha finito le richieste del giorno

Quando Google risponde "429" (quota esaurita) il programma capisce se
è un limite al minuto (aspetta e riprova) o al giorno (passa alla
chiave a pagamento e lo segnala negli avvisi).

Google ha due "porte" per parlare con Gemini: la nuova, chiamata
interactions, e la vecchia, generateContent. Si prova la nuova; se
risponde che non esiste, si usa la vecchia per il resto della notte.
"""
import base64
import io
import json
import os
import re
import time
import wave

import requests

from .llm import ErroreModello, estrai_json, pulisci_risposta

BASE = "https://generativelanguage.googleapis.com/v1beta"


class Chiavi:
    """Le chiavi in ordine di preferenza, e quale si sta usando."""

    def __init__(self, avanz, etichetta):
        self.avanz = avanz
        self.etichetta = etichetta
        self.lista = []
        for nome, descr in (("GEMINI_API_KEY_GRATIS", "gratuita"),
                            ("GEMINI_API_KEY_PAGAMENTO", "a pagamento")):
            v = os.environ.get(nome, "").strip()
            if v:
                self.lista.append((v, descr))
        if not self.lista:
            raise ErroreModello("Nessuna chiave Gemini: imposta GEMINI_API_KEY_GRATIS "
                                "(e se vuoi GEMINI_API_KEY_PAGAMENTO)")
        self.i = 0
        self.usata_pagamento = False

    @property
    def attuale(self):
        return self.lista[self.i][0]

    @property
    def tipo(self):
        return self.lista[self.i][1]

    def passa_alla_prossima(self, motivo):
        if self.i + 1 >= len(self.lista):
            return False
        self.i += 1
        if self.tipo == "a pagamento":
            self.usata_pagamento = True
        self.avanz.avviso(f"{self.etichetta}: chiave gratuita esaurita ({motivo}), "
                          f"passo alla chiave {self.tipo}")
        return True


def _ritardo_suggerito(testo):
    m = re.search(r'"retryDelay"\s*:\s*"(\d+(?:\.\d+)?)s"', testo)
    return float(m.group(1)) if m else None


def _quota_giornaliera(testo):
    return bool(re.search(r"PerDay|per.day|daily", testo, re.I))


def chiama(chiavi, url, corpo, avanz, timeout=300, tentativi=6):
    """POST con gestione di quote, errori temporanei e cambio chiave."""
    attese_minuto = 0
    ultimo = ""
    for _ in range(tentativi + len(chiavi.lista)):
        try:
            r = requests.post(url, json=corpo, timeout=timeout,
                              headers={"x-goog-api-key": chiavi.attuale,
                                       "Content-Type": "application/json"})
        except requests.RequestException as e:
            ultimo = str(e)
            time.sleep(15)
            continue
        if r.status_code == 200:
            return r.json()
        ultimo = f"{r.status_code}: {r.text[:400]}"
        if r.status_code == 429:
            ritardo = _ritardo_suggerito(r.text)
            if not _quota_giornaliera(r.text) and attese_minuto < 3:
                attese_minuto += 1
                attesa = min(max(ritardo or 30, 5), 90)
                avanz.scrivi(f"   limite al minuto raggiunto, aspetto {attesa:.0f} secondi")
                time.sleep(attesa)
                continue
            if chiavi.passa_alla_prossima("limite giornaliero" if _quota_giornaliera(r.text) else "limite raggiunto"):
                attese_minuto = 0
                continue
            raise ErroreModello("Quota Gemini esaurita anche sulla chiave di riserva. " + ultimo)
        if r.status_code in (500, 502, 503, 504):
            avanz.scrivi(f"   Gemini temporaneamente non disponibile ({r.status_code}), riprovo tra 30 secondi")
            time.sleep(30)
            continue
        # 400, 403, 404: errori della richiesta, non temporanei
        raise ErroreModello(f"Gemini ha rifiutato la richiesta ({ultimo})")
    raise ErroreModello(f"Gemini non risponde dopo vari tentativi ({ultimo})")


# ---------------------------------------------------------------------
#  Testo
# ---------------------------------------------------------------------

def _testo_interactions(d):
    if isinstance(d.get("output_text"), str) and d["output_text"].strip():
        return d["output_text"]
    pezzi = []
    for passo in d.get("steps", []) or d.get("outputs", []):
        for c in passo.get("content", []) if isinstance(passo, dict) else []:
            if c.get("type") == "text" and c.get("text"):
                pezzi.append(c["text"])
        if passo.get("type") == "text" and passo.get("text"):
            pezzi.append(passo["text"])
    return "".join(pezzi)


def _testo_generatecontent(d):
    out = []
    for cand in d.get("candidates", [])[:1]:
        for p in cand.get("content", {}).get("parts", []):
            if p.get("text") and not p.get("thought"):
                out.append(p["text"])
    return "".join(out)


class GeminiTesto:
    """Stessa interfaccia del motore Ollama: chat(), controlla(), libera()."""

    def __init__(self, cfg, avanz):
        self.cfg = cfg
        self.nome = cfg["modello"]
        self.avanz = avanz
        self.chiavi = Chiavi(avanz, "Gemini testo")
        self.porta = cfg.get("porta", "auto")   # auto, interactions, generatecontent
        self.troncato = False
        self.richieste = 0
        self._ultima = 0.0

    def controlla(self):
        pass

    def libera(self):
        pass

    def _pausa(self):
        # Il livello gratuito ha un limite di richieste al minuto: si va piano.
        attesa = self.cfg.get("pausa_tra_richieste", 0) - (time.time() - self._ultima)
        if attesa > 0:
            time.sleep(attesa)
        self._ultima = time.time()

    def chat(self, sistema, utente, compito, schema=None, temperatura=None, max_token=4096):
        temp = temperatura if temperatura is not None else self.cfg.get("temperatura_scrittura", 0.7)
        for tentativo in range(2):
            self._pausa()
            self.avanz.vivo(f"{compito}: in attesa di Gemini ({self.nome}, chiave {self.chiavi.tipo})")
            inizio = time.time()
            testo = self._una_richiesta(sistema, utente, schema, temp, max_token)
            self.richieste += 1
            self.avanz.vivo(f"{compito}: {len(testo.split())} parole in {time.time() - inizio:.0f} s")
            if not schema:
                return pulisci_risposta(testo)
            try:
                return json.loads(estrai_json(testo))
            except ValueError:
                self.avanz.scrivi(f"   risposta non in formato JSON ({compito}), riprovo")
                temp = 0.1
        raise ErroreModello(f"Gemini non ha prodotto un JSON valido per «{compito}»")

    def _una_richiesta(self, sistema, utente, schema, temp, max_token):
        if self.porta in ("auto", "interactions"):
            corpo = {"model": self.nome, "input": f"{sistema}\n\n{utente}",
                     "generation_config": {"temperature": temp}}
            if schema:
                corpo["response_format"] = {"type": "text", "mime_type": "application/json",
                                            "schema": schema}
            try:
                d = chiama(self.chiavi, f"{BASE}/interactions", corpo, self.avanz)
                self.troncato = "MAX_TOKENS" in json.dumps(d)[-2000:]
                if self.porta == "auto":
                    self.porta = "interactions"
                return _testo_interactions(d)
            except ErroreModello as e:
                if self.porta == "interactions" or not re.search(r"\b(400|404)\b", str(e)):
                    raise
                self.avanz.scrivi("   la porta 'interactions' non risponde, uso generateContent")
                self.porta = "generatecontent"

        corpo = {"systemInstruction": {"parts": [{"text": sistema}]},
                 "contents": [{"role": "user", "parts": [{"text": utente}]}],
                 "generationConfig": {"temperature": temp, "maxOutputTokens": max(max_token, 8192)}}
        if schema:
            corpo["generationConfig"]["responseMimeType"] = "application/json"
            corpo["generationConfig"]["responseJsonSchema"] = schema
        d = chiama(self.chiavi, f"{BASE}/models/{self.nome}:generateContent", corpo, self.avanz)
        cand = (d.get("candidates") or [{}])[0]
        self.troncato = cand.get("finishReason") == "MAX_TOKENS"
        return _testo_generatecontent(d)


# ---------------------------------------------------------------------
#  Voce
# ---------------------------------------------------------------------

def _wav_da_pcm(pcm, freq=24000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(freq)
        w.writeframes(pcm)
    return buf.getvalue()


def _audio_interactions(d):
    pezzi = []
    for passo in d.get("steps", []):
        for c in passo.get("content", []):
            if c.get("type") == "audio" and c.get("data"):
                pezzi.append(c["data"])
    if not pezzi:
        return None
    dati = base64.b64decode(pezzi[-1])
    return dati if dati[:4] == b"RIFF" else _wav_da_pcm(dati)


def _audio_generatecontent(d):
    for cand in d.get("candidates", [])[:1]:
        for p in cand.get("content", {}).get("parts", []):
            inl = p.get("inlineData") or p.get("inline_data")
            if inl and inl.get("data"):
                dati = base64.b64decode(inl["data"])
                m = re.search(r"rate=(\d+)", inl.get("mimeType", ""))
                return dati if dati[:4] == b"RIFF" else _wav_da_pcm(dati, int(m.group(1)) if m else 24000)
    return None


class GeminiVoce:
    def __init__(self, cfg, lingua, avanz):
        self.cfg = cfg
        self.nome = cfg["modello"]
        self.lingua = lingua
        self.avanz = avanz
        self.chiavi = Chiavi(avanz, "Gemini voce")
        self.porta = cfg.get("porta", "auto")
        self.richieste = 0

    def blocco(self, battute):
        """Genera un blocco di battute a due voci. Ritorna i byte di un file WAV."""
        nomi = self.lingua["conduttori"]
        voci = self.cfg["voci"]
        stili = self.cfg.get("stili", {})
        guida = self.cfg.get("istruzioni", "")
        time.sleep(self.cfg.get("pausa_tra_richieste", 0))
        self.richieste += 1

        if self.porta in ("auto", "interactions"):
            contenuto = []
            for chi, testo in battute:
                ann = {"type": "speech_metadata", "speaker": nomi[chi]}
                if stili.get(chi):
                    ann["style"] = stili[chi]
                contenuto.append({"type": "text", "text": testo, "annotations": [ann]})
            corpo = {"model": self.nome,
                     "input": [{"type": "user_input", "content": contenuto}],
                     "response_format": {"type": "audio"},
                     "generation_config": {"speech_config": {
                         "mode": "conversational",
                         "speakers": [{"speaker": nomi[k], "voice": voci[k]} for k in nomi]}}}
            try:
                d = chiama(self.chiavi, f"{BASE}/interactions", corpo, self.avanz, timeout=600)
                if self.porta == "auto":
                    self.porta = "interactions"
                audio = _audio_interactions(d)
                if audio:
                    return audio
                raise ErroreModello("Gemini voce: risposta senza audio")
            except ErroreModello as e:
                if self.porta == "interactions" or not re.search(r"\b(400|404)\b", str(e)):
                    raise
                self.avanz.scrivi("   voce: la porta 'interactions' non risponde, uso generateContent")
                self.porta = "generatecontent"

        copione = "\n".join(f"{nomi[chi]}: {t}" for chi, t in battute)
        testo = (f"{guida}\n\n{copione}" if guida else copione)
        corpo = {"contents": [{"parts": [{"text": testo}]}],
                 "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                     "multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                         {"speaker": nomi[k], "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voci[k]}}}
                         for k in nomi]}}}}
        d = chiama(self.chiavi, f"{BASE}/models/{self.nome}:generateContent", corpo, self.avanz, timeout=600)
        audio = _audio_generatecontent(d)
        if not audio:
            raise ErroreModello("Gemini voce: risposta senza audio")
        return audio


# ---------------------------------------------------------------------
#  Immagine
# ---------------------------------------------------------------------

def _immagine_interactions(d):
    oi = d.get("output_image")
    if isinstance(oi, str):
        return base64.b64decode(oi)
    if isinstance(oi, dict) and oi.get("data"):
        return base64.b64decode(oi["data"])
    for passo in d.get("steps", []):
        for c in passo.get("content", []):
            if c.get("type") == "image" and c.get("data"):
                return base64.b64decode(c["data"])
    return None


def _immagine_generatecontent(d):
    for cand in d.get("candidates", [])[:1]:
        for p in cand.get("content", {}).get("parts", []):
            inl = p.get("inlineData") or p.get("inline_data")
            if inl and inl.get("data"):
                return base64.b64decode(inl["data"])
    return None


class GeminiImmagine:
    def __init__(self, cfg, avanz):
        self.cfg = cfg
        self.nome = cfg["modello"]
        self.avanz = avanz
        self.chiavi = Chiavi(avanz, "Gemini immagine")
        self.porta = cfg.get("porta", "auto")

    def genera(self, soggetto):
        richiesta = self.cfg["prompt"].replace("{soggetto}", soggetto.strip().rstrip("."))
        if self.porta in ("auto", "interactions"):
            corpo = {"model": self.nome,
                     "input": [{"type": "text", "text": richiesta}],
                     "response_format": {"type": "image", "aspect_ratio": "1:1", "image_size": "1K"}}
            try:
                d = chiama(self.chiavi, f"{BASE}/interactions", corpo, self.avanz, timeout=300)
                img = _immagine_interactions(d)
                if img:
                    return img
                raise ErroreModello("Gemini immagine: risposta senza immagine")
            except ErroreModello as e:
                if self.porta == "interactions" or not re.search(r"\b(400|404)\b", str(e)):
                    raise
                self.porta = "generatecontent"
        corpo = {"contents": [{"parts": [{"text": richiesta}]}],
                 "generationConfig": {"responseModalities": ["IMAGE"],
                                      "imageConfig": {"aspectRatio": "1:1"}}}
        d = chiama(self.chiavi, f"{BASE}/models/{self.nome}:generateContent", corpo, self.avanz, timeout=300)
        img = _immagine_generatecontent(d)
        if not img:
            raise ErroreModello("Gemini immagine: risposta senza immagine")
        return img


# ---------------------------------------------------------------------
#  Musica (Lyria): si usa una volta sola, per creare la sigla
# ---------------------------------------------------------------------

def _audio_qualsiasi(d):
    """Estrae l'audio da una risposta, in qualunque formato arrivi."""
    oa = d.get("output_audio")
    if isinstance(oa, str):
        return base64.b64decode(oa)
    if isinstance(oa, dict) and oa.get("data"):
        return base64.b64decode(oa["data"])
    for passo in d.get("steps", []):
        for c in passo.get("content", []):
            if c.get("type") == "audio" and c.get("data"):
                return base64.b64decode(c["data"])
    for cand in d.get("candidates", [])[:1]:
        for p in cand.get("content", {}).get("parts", []):
            inl = p.get("inlineData") or p.get("inline_data")
            if inl and inl.get("data"):
                return base64.b64decode(inl["data"])
    return None


def estensione_audio(dati):
    if dati[:4] == b"RIFF":
        return ".wav"
    if dati[:3] == b"ID3" or dati[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return ".mp3"
    if dati[:4] == b"fLaC":
        return ".flac"
    if dati[:4] == b"OggS":
        return ".ogg"
    return ".bin"


class GeminiMusica:
    def __init__(self, modello, avanz):
        self.nome = modello
        self.avanz = avanz
        self.chiavi = Chiavi(avanz, "Lyria")

    def genera(self, descrizione):
        d = chiama(self.chiavi, f"{BASE}/interactions", {"model": self.nome, "input": descrizione},
                   self.avanz, timeout=600)
        audio = _audio_qualsiasi(d)
        if not audio:
            raise ErroreModello("Lyria: risposta senza audio (" + json.dumps(d)[:300] + ")")
        return audio

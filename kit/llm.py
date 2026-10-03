"""Collegamento al modello di testo.

Ollama è il programma che tiene i modelli e risponde a domande via
"API" (una porta di servizio su http://127.0.0.1:11434).
Il motore Finto serve a provare tutto il resto senza modello.
"""
import json
import re
import time

import requests


class ErroreModello(RuntimeError):
    pass


class Ollama:
    def __init__(self, cfg, avanz):
        self.url = cfg["indirizzo"].rstrip("/")
        self.nome = cfg["nome"]
        self.cfg = cfg
        self.avanz = avanz
        self.troncato = False

    def controlla(self):
        try:
            r = requests.get(f"{self.url}/api/tags", timeout=10)
        except requests.RequestException:
            raise ErroreModello("Ollama non risponde. È avviato? (sudo systemctl start ollama)")
        nomi = {m["name"] for m in r.json().get("models", [])}
        if self.nome not in nomi and f"{self.nome}:latest" not in nomi:
            raise ErroreModello(f"Il modello {self.nome} non è installato. Comando: ollama pull {self.nome}")

    def chat(self, sistema, utente, compito, schema=None, temperatura=None, max_token=4096):
        corpo = {
            "model": self.nome,
            "messages": [{"role": "system", "content": sistema},
                         {"role": "user", "content": utente}],
            "stream": True,
            "keep_alive": "15m",
            "options": {
                "num_ctx": self.cfg["contesto"],
                "temperature": temperatura if temperatura is not None else self.cfg["temperatura_scrittura"],
                "num_predict": max_token,
            },
        }
        if self.cfg.get("disattiva_ragionamento"):
            corpo["think"] = False
        if schema:
            corpo["format"] = schema

        for tentativo in range(2):
            testo = self._flusso(corpo, compito)
            if not schema:
                return pulisci_risposta(testo)
            try:
                return json.loads(estrai_json(testo))
            except ValueError:
                self.avanz.scrivi(f"   risposta non in formato JSON ({compito}), riprovo")
                corpo["options"]["temperature"] = 0.1
        raise ErroreModello(f"Il modello non ha prodotto un JSON valido per «{compito}»")

    def _flusso(self, corpo, compito):
        inizio = time.time()
        pezzi = []
        self.troncato = False
        try:
            with requests.post(f"{self.url}/api/chat", json=corpo, stream=True,
                               timeout=(10, self.cfg["timeout"])) as r:
                if r.status_code != 200:
                    raise ErroreModello(f"Ollama ha risposto {r.status_code}: {r.text[:300]}")
                for riga in r.iter_lines():
                    if not riga:
                        continue
                    d = json.loads(riga)
                    if d.get("error"):
                        raise ErroreModello(d["error"])
                    pezzi.append(d.get("message", {}).get("content", ""))
                    if len(pezzi) % 8 == 0:
                        parole = len("".join(pezzi).split())
                        sec = time.time() - inizio
                        self.avanz.vivo(f"{compito}: {parole} parole, {sec:.0f} s")
                    if time.time() - inizio > self.cfg["timeout"]:
                        raise ErroreModello(f"«{compito}» oltre il tempo massimo")
                    if d.get("done"):
                        # "length": il modello si è fermato perché ha finito lo spazio, non perché aveva finito.
                        self.troncato = d.get("done_reason") == "length"
                        break
        except requests.RequestException as e:
            raise ErroreModello(f"Collegamento con Ollama interrotto: {e}")
        return "".join(pezzi)

    def libera(self):
        """Toglie il modello dalla memoria video, per lasciare posto a voce e immagini."""
        try:
            requests.post(f"{self.url}/api/generate",
                          json={"model": self.nome, "keep_alive": 0}, timeout=30)
        except requests.RequestException:
            pass


def estrai_json(testo):
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", testo.strip())
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i >= 0 and j > i else t


def pulisci_risposta(testo):
    t = re.sub(r"<think>.*?</think>", "", testo, flags=re.S)
    t = re.sub(r"^```\w*\s*|\s*```$", "", t.strip())
    return t.strip()


# ---------------------------------------------------------------------
#  Motore finto: risposte plausibili per collaudare il flusso.
# ---------------------------------------------------------------------

class Finto:
    nome = "finto"

    troncato = False

    def __init__(self, avanz, lingua):
        self.avanz = avanz
        self.lingua = lingua

    def controlla(self):
        pass

    def libera(self):
        pass

    def chat(self, sistema, utente, compito, schema=None, temperatura=None, max_token=4096):
        self.avanz.vivo(f"{compito}: (motore finto)")
        time.sleep(0.05)
        f = getattr(self, "_" + compito.split(":")[0].replace(" ", "_"), None)
        if f is None:
            raise ErroreModello(f"motore finto: compito sconosciuto {compito}")
        return f(utente)

    @staticmethod
    def _tra_marcatori(testo):
        m = re.search(r"<<<(.*?)>>>", testo, re.S)
        return m.group(1).strip() if m else ""

    def _estrai(self, u):
        t = self._tra_marcatori(u)
        fr = [f for f in re.split(r"(?<=[.!?])\s+", t) if 40 < len(f) < 220][:5]
        num = re.findall(r"\b\d+(?:[.,]\d+)?%?", t)[:3]
        return {"fatti": fr, "numeri": [{"valore": n, "cosa_misura": "valore citato nel testo"} for n in num],
                "esempi": fr[:1], "limiti": [], "termini": []}

    def _scheda(self, u):
        return {
            "nome_breve": "SistemaDiProva",
            "problema": "I modelli che guardano video in diretta dimenticano cose che poi servono.",
            "idea": "Tenere una memoria ordinata di ciò che si è visto e rispondere al momento giusto.",
            "come_funziona": ["Guarda il video a pezzi.", "Annota i fatti utili.", "Risponde quando serve."],
            "risultati": [{"fatto": "Migliora i risultati sui test usati dagli autori", "numero": "157"}],
            "limiti": ["Provato solo su test costruiti dagli autori."],
            "esempio_concreto": "Un assistente negli occhiali smart che ricorda dove hai lasciato le chiavi.",
            "perche_ti_riguarda": "Gli assistenti che vedono con te diventano più utili.",
            "gancio": "Hai mai chiesto a qualcuno dove hai messo le chiavi?",
            "termini": [{"termine": "Hugging Face", "tipo": "nome", "espansione_inglese": "",
                         "spiegazione": "sito dove si condividono modelli di AI", "usa": "termine",
                         "pronuncia": "Hàghing Féis"},
                        {"termine": "LLM", "tipo": "sigla", "espansione_inglese": "Large Language Model",
                         "spiegazione": "grande modello linguistico", "usa": "spiegazione",
                         "pronuncia": "elle elle emme"}],
            "soggetto_immagine": "una pellicola che si avvolge attorno a un piccolo quaderno di appunti",
            "hashtag": ["AI", "Video", "Memoria", "Assistenti", "MachineLearning"],
        }

    def _dialogo(self, u):
        n = re.search(r"puntata numero (\d+)|episode number (\d+)", u)
        num = (n.group(1) or n.group(2)) if n else "1"
        righe = ["ARIANNA: Hai mai chiesto a qualcuno dove hai messo le chiavi?",
                 "CARLO: Mille volte. E di solito nessuno lo sa.",
                 f"ARIANNA: Benvenuti ad AI Paper in Pillole, puntata numero {num}. Io sono Arianna.",
                 "CARLO: E io sono Carlo. Oggi parliamo di un sistema che guarda video e ricorda."]
        for i in range(34):
            chi = "CARLO" if i % 2 else "ARIANNA"
            righe.append(f"{chi}: Questa è una battuta di prova numero {i} per misurare la lunghezza del dialogo. "
                         f"Serve solo a collaudare il montaggio e i controlli automatici.")
        righe += ["ARIANNA: Se la puntata ti è piaciuta, lascia un like e cinque stelline.",
                  "CARLO: E seguici, così domani non ti perdi il prossimo paper. Un abbraccio, a domani!"]
        return "\n".join(righe)

    def _riscrivi(self, u):
        t = self._tra_marcatori(u)
        return re.sub(r"(?i)assolutamente!?|esatto!?|ottima domanda!?|wow!?", "", t).strip() or t

    def _lunghezza(self, u):
        return self._tra_marcatori(u)

    def _struttura(self, u):
        return self._dialogo(u)

    def _titolo(self, u):
        return {"nome": "SistemaDiProva", "sottotitolo": "quando l'AI guarda un video e se lo ricorda"}

    def _descrizione(self, u):
        return ("Paragrafo di prova uno. Descrive il problema in parole semplici.\n\n"
                "Paragrafo di prova due. Spiega l'idea del paper.\n\n"
                "Paragrafo di prova tre. Riporta i risultati.")

    def _articolo(self, u):
        corpo = " ".join(["Frase di prova per l'articolo divulgativo."] * 20)
        return "\n\n".join(f"## Sottotitolo {i}\n\n{corpo}" for i in range(1, 7))

    def _correggi(self, u):
        return self._tra_marcatori(u)

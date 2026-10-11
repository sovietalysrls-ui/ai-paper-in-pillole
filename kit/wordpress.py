"""Passo 10: l'articolo su WordPress, tramite la REST API.

La REST API è la porta di servizio di WordPress per i programmi.
L'accesso usa una "password per applicazioni": si crea in
Bacheca > Utenti > Profilo, si può revocare quando si vuole, e non
è la password con cui entri nel sito.

Cosa fa: carica la copertina, la imposta come immagine in evidenza,
trova o crea la categoria e i tag, crea l'articolo in bozza o
pubblicato secondo config.yaml.
"""
import os
import socket
import time
from pathlib import Path

import requests
import urllib3.util.connection as _conn

# I computer di GitHub non hanno IPv6: si forza IPv4, altrimenti la
# connessione al sito fallisce con "Network is unreachable".
_conn.allowed_gai_family = lambda: socket.AF_INET


class ErroreWordPress(RuntimeError):
    pass


class WordPress:
    def __init__(self, sito):
        self.base = sito.rstrip("/") + "/wp-json/wp/v2"
        utente = os.environ.get("WP_UTENTE", "").strip()
        password = os.environ.get("WP_PASSWORD_APP", "").strip()
        if not utente or not password:
            raise ErroreWordPress("Mancano WP_UTENTE e WP_PASSWORD_APP nei segreti")
        self.s = requests.Session()
        self.s.auth = (utente, password)
        self.s.headers["User-Agent"] = "AI-Paper-in-Pillole/1.0"

    def _r(self, metodo, percorso, **kw):
        ultimo = None
        for tentativo in range(3):
            try:
                # Un server irraggiungibile deve fallire presto; 90 secondi restano
                # disponibili per leggere risposte lente dopo che la connessione è aperta.
                r = self.s.request(metodo, self.base + percorso, timeout=(20, 90),
                                   allow_redirects=False, **kw)
                break
            except requests.RequestException as e:
                ultimo = e
                time.sleep(10)
        else:
            raise ErroreWordPress(f"sito non raggiungibile: {ultimo}")
        if r.status_code in (301, 302, 307, 308):
            raise ErroreWordPress(f"il sito rimanda a {r.headers.get('Location')}: "
                                  "correggi 'sito' in config.yaml con quell'indirizzo")
        if r.status_code == 401:
            raise ErroreWordPress("accesso rifiutato (401): controlla utente e password per applicazioni. "
                                  "Alcuni hosting bloccano l'accesso dei programmi: va abilitato.")
        if r.status_code >= 400:
            raise ErroreWordPress(f"{metodo} {percorso} → {r.status_code}: {r.text[:300]}")
        return r.json()

    def _termine(self, tipo, nome):
        trovati = self._r("GET", f"/{tipo}", params={"search": nome, "per_page": 100})
        for t in trovati:
            if t["name"].strip().lower() == nome.strip().lower():
                return t["id"]
        return self._r("POST", f"/{tipo}", json={"name": nome})["id"]

    def carica_immagine(self, percorso, titolo):
        dati = Path(percorso).read_bytes()
        nome = Path(percorso).name
        return self._r("POST", "/media", data=dati, headers={
            "Content-Disposition": f'attachment; filename="{nome}"',
            "Content-Type": "image/jpeg"})["id"], titolo

    def pubblica_bozza(self, id_post):
        """Pubblica un articolo che è in bozza."""
        p = self._r("POST", f"/posts/{id_post}", json={"status": "publish"})
        return {"id": p["id"], "link": p.get("link"), "stato": p.get("status")}

    def pubblica(self, titolo, html, estratto, categoria, tag, copertina, stato, chiave, sostituisci=False):
        """chiave: un identificativo (l'id arXiv) per non creare doppioni se si rilancia.
        sostituisci: se l'articolo esiste già, ne aggiorna testo, titolo e copertina
        (lo stato, bozza o pubblicato, resta quello che ha)."""
        esistenti = self._r("GET", "/posts", params={"search": chiave, "status": "draft,publish,future,pending",
                                                     "per_page": 5, "context": "edit"})
        for p in esistenti:
            if chiave in (p.get("content", {}).get("raw", "") or ""):
                if not sostituisci:
                    if stato == "pubblica" and p.get("status") == "draft":
                        # c'era già in bozza (da un tentativo precedente): ora va pubblicato
                        p = self._r("POST", f"/posts/{p['id']}", json={"status": "publish"})
                    return {"id": p["id"], "link": p.get("link"), "stato": p.get("status"), "esisteva": True}
                corpo = {"title": titolo, "content": html, "excerpt": estratto}
                if copertina and Path(copertina).exists():
                    id_media, _ = self.carica_immagine(copertina, titolo)
                    self._r("POST", f"/media/{id_media}", json={"alt_text": titolo, "title": titolo})
                    corpo["featured_media"] = id_media
                q = self._r("POST", f"/posts/{p['id']}", json=corpo)
                return {"id": q["id"], "link": q.get("link"), "stato": q.get("status"),
                        "esisteva": True, "aggiornato": True}

        id_cat = self._termine("categories", categoria)
        id_tag = [self._termine("tags", t) for t in tag[:6]]
        id_media = None
        if copertina and Path(copertina).exists():
            id_media, _ = self.carica_immagine(copertina, titolo)
            self._r("POST", f"/media/{id_media}", json={"alt_text": titolo, "title": titolo})
        corpo = {"title": titolo, "content": html, "excerpt": estratto,
                 "status": "publish" if stato == "pubblica" else "draft",
                 "categories": [id_cat], "tags": id_tag}
        if id_media:
            corpo["featured_media"] = id_media
        p = self._r("POST", "/posts", json=corpo)
        return {"id": p["id"], "link": p.get("link"), "stato": p.get("status"), "esisteva": False}

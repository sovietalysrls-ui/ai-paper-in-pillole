"""Registro dei paper usati e dei numeri di puntata.

È un database SQLite: un unico file (dati/registro.sqlite) che
il programma interroga come una piccola tabella Excel.
"""
import datetime as dt
import sqlite3
from pathlib import Path


class Registro:
    def __init__(self, cartella_base):
        p = Path(cartella_base) / "dati" / "registro.sqlite"
        p.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(p)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS puntate (
                arxiv_id TEXT, lingua TEXT, stato TEXT, data TEXT,
                numero INTEGER, titolo TEXT, voti INTEGER,
                aggiornato TEXT,
                PRIMARY KEY (arxiv_id, lingua));
            CREATE TABLE IF NOT EXISTS scartati (
                arxiv_id TEXT PRIMARY KEY, motivo TEXT, data TEXT);
        """)
        self.db.commit()

    # Paper da non riproporre: completati, in lavorazione oggi, scartati.
    def esclusi(self, lingua):
        r = {a for (a,) in self.db.execute(
            "SELECT arxiv_id FROM puntate WHERE lingua=? AND stato='completa'", (lingua,))}
        r |= {a for (a,) in self.db.execute("SELECT arxiv_id FROM scartati")}
        return r

    def scarta(self, arxiv_id, motivo):
        self.db.execute("INSERT OR REPLACE INTO scartati VALUES (?,?,?)",
                        (arxiv_id, motivo, dt.date.today().isoformat()))
        self.db.commit()

    def prossimo_numero(self, lingua, iniziale):
        (m,) = self.db.execute(
            "SELECT MAX(numero) FROM puntate WHERE lingua=? AND stato='completa'",
            (lingua,)).fetchone()
        return (m + 1) if m else iniziale

    def segna(self, arxiv_id, lingua, stato, data, numero, titolo="", voti=0):
        self.db.execute(
            "INSERT OR REPLACE INTO puntate VALUES (?,?,?,?,?,?,?,?)",
            (arxiv_id, lingua, stato, data, numero, titolo, voti,
             dt.datetime.now().isoformat(timespec="seconds")))
        self.db.commit()

    def elenco(self, lingua, n=20):
        return self.db.execute(
            "SELECT data, numero, arxiv_id, stato, titolo FROM puntate "
            "WHERE lingua=? ORDER BY data DESC, numero DESC LIMIT ?", (lingua, n)).fetchall()

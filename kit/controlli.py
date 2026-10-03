"""Controlli automatici sul dialogo e versione "da leggere" per la voce.

Nessun modello qui: solo regole. Trovano i problemi e dicono quale
battuta va riscritta. La riscrittura la fa testi.py.
"""
import datetime as dt
import json
import re

from .util import conta_parole, frasi


# ---------------------------------------------------------------------
#  Lettura del dialogo
# ---------------------------------------------------------------------

def analizza(testo, lingua):
    """Trasforma il testo del modello in una lista di (CHI, battuta)."""
    nomi = lingua["conduttori"]  # es. {"CARLO": "Carlo", "ARIANNA": "Arianna"}
    rx = re.compile(r"^[\s*_#>-]*(" + "|".join(map(re.escape, nomi.values())) +
                    r")[\s*_]*[:：][\s*_]*(.*)$", re.I)
    battute = []
    for riga in testo.splitlines():
        riga = riga.strip()
        if not riga or re.fullmatch(r"[\[(].*[\])]", riga) or riga.startswith("---"):
            continue
        m = rx.match(riga)
        if m:
            chi = next(k for k, v in nomi.items() if v.lower() == m.group(1).lower())
            battute.append([chi, m.group(2)])
        elif battute:
            battute[-1][1] += " " + riga
    pulite = []
    for chi, b in battute:
        b = re.sub(r"\[[^\]]*\]|\*\([^)]*\)\*|\*+", "", b)   # didascalie e grassetti
        b = " ".join(b.split()).strip()
        if b:
            pulite.append((chi, b))
    return pulite


def componi(battute, lingua):
    return "\n\n".join(f"{lingua['conduttori'][chi]}: {b}" for chi, b in battute)


def componi_tecnico(battute):
    return "\n".join(f"{chi}: {b}" for chi, b in battute)


# ---------------------------------------------------------------------
#  Controlli
# ---------------------------------------------------------------------

def _numeri(testo):
    """Numeri presenti nel testo, normalizzati: 96,0 e 96 diventano "96"."""
    out = set()
    for n in re.findall(r"\d+(?:[.,]\d+)?", testo):
        try:
            out.add(f"{float(n.replace(',', '.')):g}")
        except ValueError:
            pass
    return out


def controlla(battute, scheda, lingua, cfg_d, numero_puntata):
    per_battuta = {}
    globali = []

    def segnala(i, motivo):
        per_battuta.setdefault(i, []).append(motivo)

    vietate = [(re.compile(v["regex"], re.I | re.M), v["motivo"]) for v in lingua["vietate"]]
    testo_scheda = json.dumps(scheda, ensure_ascii=False)
    numeri_ok = _numeri(testo_scheda) | {str(numero_puntata), str(dt.date.today().year)}
    T = lingua["testi_controlli"]

    for i, (chi, b) in enumerate(battute):
        for rx, motivo in vietate:
            if rx.search(b):
                segnala(i, T["vietata"].format(motivo=motivo))
        if i > 0:
            inizio = " ".join(re.findall(r"\w+", b.lower())[:4])
            prec = " ".join(re.findall(r"\w+", battute[i - 1][1].lower()))
            if len(inizio.split()) == 4 and inizio in prec:
                segnala(i, T["eco"])
        for f in frasi(b):
            if conta_parole(f) > cfg_d["parole_max_frase"]:
                segnala(i, T["frase_lunga"].format(n=conta_parole(f)))
                break
        for n in _numeri(b):
            try:
                if float(n) <= 10:
                    continue
            except ValueError:
                pass
            if n not in numeri_ok:
                segnala(i, T["numero"].format(n=n))

    # Frasi ripetute identiche: segno che il modello si è "incantato".
    viste = {}
    for i, (_, b) in enumerate(battute):
        for f in frasi(b):
            chiave = " ".join(re.findall(r"\w+", f.lower()))
            if conta_parole(chiave) < 5:
                continue
            if chiave in viste and viste[chiave] != i:
                segnala(i, T["ripetuta"])
                break
            viste.setdefault(chiave, i)

    # Sigle: spiegata una volta sola, e in una lingua sola.
    testo_tutto = [b.lower() for _, b in battute]
    for t in scheda.get("termini", []):
        if t.get("tipo") != "sigla":
            continue
        en = (t.get("espansione_inglese") or "").lower().strip()
        loc = (t.get("spiegazione") or "").lower().strip()
        visti_en = [i for i, b in enumerate(testo_tutto) if en and en in b]
        visti_loc = [i for i, b in enumerate(testo_tutto) if loc and len(loc) > 6 and loc in b]
        if en and loc and en != loc and visti_en and visti_loc:
            segnala(max(visti_en[0], visti_loc[0]), T["sigla_doppia"].format(s=t["termine"]))
        for vis in (visti_en, visti_loc):
            for i in vis[1:]:
                segnala(i, T["sigla_ripetuta"].format(s=t["termine"]))

    # Struttura: gancio, presentazione, chiusura.
    nome = lingua["nome_podcast"].lower()
    primi = [b.lower() for _, b in battute[:6]]
    if not any(nome in b for b in primi):
        globali.append(("struttura", T["manca_presentazione"]))
    elif nome in primi[0]:
        globali.append(("struttura", T["manca_gancio"]))
    ultimi = " ".join(b.lower() for _, b in battute[-4:])
    mancanti = [p for p in lingua["parole_chiusura"] if not re.search(p, ultimi)]
    if mancanti:
        globali.append(("struttura", T["manca_chiusura"].format(cosa=", ".join(mancanti))))
    if len({chi for chi, _ in battute}) < 2:
        globali.append(("struttura", T["una_voce"]))

    # Lunghezza.
    parole = sum(conta_parole(b) for _, b in battute)
    massimo = int(cfg_d["secondi_max"] / 60 * cfg_d["parole_al_minuto"])
    if parole > massimo:
        globali.append(("lunghezza", T["troppo_lungo"].format(n=parole, max=massimo), massimo - 30))
    elif parole < cfg_d["parole_min"]:
        globali.append(("lunghezza", T["troppo_corto"].format(n=parole, min=cfg_d["parole_min"]),
                        cfg_d["parole_min"] + 60))
    return per_battuta, globali, parole, massimo


# ---------------------------------------------------------------------
#  Versione per la voce: nomi stranieri scritti come si pronunciano
# ---------------------------------------------------------------------

def mappa_pronuncia(lingua, scheda):
    """Dizionario fisso + proposte del modello. Il fisso vince sempre."""
    mappa = {}
    for t in scheda.get("termini", []):
        p = (t.get("pronuncia") or "").strip()
        termine = (t.get("termine") or "").strip()
        if not p or not termine or p.lower() == termine.lower():
            continue
        if t.get("tipo") == "sigla" and t.get("usa") == "spiegazione":
            continue
        mappa[termine] = p
    proposte = {k: v for k, v in mappa.items() if k not in lingua["pronuncia_fissa"]}
    mappa.update(lingua["pronuncia_fissa"])
    return mappa, proposte


def versione_voce(battute, mappa):
    chiavi = sorted(mappa, key=len, reverse=True)
    if not chiavi:
        return list(battute)
    rx = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, chiavi)) + r")(?![\w-])")
    return [(chi, rx.sub(lambda m: mappa[m.group(1)], b)) for chi, b in battute]

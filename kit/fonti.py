"""Passi 1 e 2: scelta del paper e lettura da arXiv."""
import datetime as dt
import re
import time

import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "AI-Paper-in-Pillole/1.0 (podcast divulgativo; andreamanini.it)"}

# ---------------------------------------------------------------------
#  Rete con tentativi ripetuti
# ---------------------------------------------------------------------

def scarica(url, tentativi=4, timeout=60, accetta=(200, 404)):
    ultimo = None
    for i in range(tentativi):
        try:
            r = requests.get(url, headers=UA, timeout=timeout)
            if r.status_code in accetta:
                return r
            ultimo = f"codice {r.status_code}"
        except requests.RequestException as e:
            ultimo = str(e)
        time.sleep(10 * (i + 1))
    raise RuntimeError(f"{url} non risponde ({ultimo})")


# ---------------------------------------------------------------------
#  Passo 1: scelta
# ---------------------------------------------------------------------

def lista_hf(data):
    # 400 = data non valida o futura: la si tratta come "nessuna lista".
    r = scarica(f"https://huggingface.co/api/daily_papers?date={data}", accetta=(200, 400, 404))
    if r.status_code != 200:
        return []
    voci = []
    for e in r.json():
        p = e.get("paper", {})
        if not p.get("id"):
            continue
        voci.append({
            "arxiv_id": p["id"],
            "titolo": " ".join((p.get("title") or e.get("title") or "").split()),
            "voti": p.get("upvotes", 0),
            "abstract": " ".join((p.get("summary") or "").split()),
            "autori": [a.get("name") for a in p.get("authors", []) if a.get("name")],
            "github": p.get("githubRepo"),
            "lista_del": data,
        })
    voci.sort(key=lambda v: -v["voti"])
    return voci


def candidati(cfg_scelta, oggi):
    """Paper in ordine di preferenza: lista più recente prima, per voti."""
    inizio = oggi - dt.timedelta(days=1 if cfg_scelta.get("parti_da_ieri", True) else 0)
    tutti, liste_viste = [], []
    for i in range(cfg_scelta.get("giorni_indietro", 7)):
        d = (inizio - dt.timedelta(days=i)).isoformat()
        voci = lista_hf(d)
        if voci:
            liste_viste.append((d, len(voci)))
            tutti.extend(v for v in voci if v["voti"] >= cfg_scelta.get("voti_minimi", 0))
    return tutti, liste_viste


# ---------------------------------------------------------------------
#  Metadati arXiv (autori, commenti tipo "22 pages, 11 figures")
# ---------------------------------------------------------------------

def metadati_arxiv(arxiv_id):
    r = scarica(f"https://export.arxiv.org/api/query?id_list={arxiv_id}")
    s = BeautifulSoup(r.text, "lxml-xml")
    voce = s.find("entry")
    if not voce or not voce.find("title"):
        return {}
    commento = voce.find("arxiv:comment") or voce.find("comment")
    return {
        "titolo": " ".join(voce.find("title").get_text().split()),
        "autori": [a.find("name").get_text(strip=True) for a in voce.find_all("author")],
        "commento": " ".join(commento.get_text().split()) if commento else "",
        "abstract": " ".join(voce.find("summary").get_text().split()) if voce.find("summary") else "",
    }


def pagine_figure(commento):
    pag = re.search(r"(\d+)\s*pages?", commento or "", re.I)
    fig = re.search(r"(\d+)\s*figures?", commento or "", re.I)
    return (int(pag.group(1)) if pag else None, int(fig.group(1)) if fig else None)


# ---------------------------------------------------------------------
#  Passo 2: lettura selettiva
# ---------------------------------------------------------------------

SALTA = re.compile(
    r"related work|prior work|literature|background|preliminar|notation|acknowledg|"
    r"reference|bibliograph|appendix|ethic|reproducib|author contribution|"
    r"impact statement|broader impact|checklist|supplementary", re.I)

# Peso: quanto conta ogni tipo di sezione (più alto = più parole tenute).
PESI = [
    (re.compile(r"introduction|overview", re.I), 1.0),
    (re.compile(r"conclusion|discussion|limitation|future work|summary", re.I), 1.0),
    (re.compile(r"experiment|result|evaluation|benchmark|analysis|ablation|finding", re.I), 1.0),
    (re.compile(r"method|approach|framework|model|architecture|design|system|pipeline", re.I), 0.8),
]


def _pulisci_nodo(nodo):
    # Formule: si tiene la versione testuale corta, si scartano quelle lunghe.
    for m in nodo.select("math"):
        alt = m.get("alttext", "")
        m.replace_with(f" {alt} " if 0 < len(alt) <= 25 else " [formula] ")
    for sel in ("cite", ".ltx_cite", ".ltx_bibliography", "table", ".ltx_tabular",
                "figure", ".ltx_note_outer", "script", "style", ".ltx_equation",
                ".ltx_equationgroup", "nav", "footer"):
        for x in nodo.select(sel):
            x.decompose()
    return nodo


def _testo(nodo):
    paragrafi = []
    for p in nodo.select("p, li.ltx_item > .ltx_para"):
        t = " ".join(p.get_text(" ").split())
        t = re.sub(r"\s+([,.;:)])", r"\1", t)
        if len(t) > 30 and t not in paragrafi:
            paragrafi.append(t)
    return "\n\n".join(paragrafi)


def _taglia(testo, parole_max):
    parole = testo.split(" ")
    if len(parole) <= parole_max:
        return testo
    return " ".join(parole[:parole_max]) + " […]"


def leggi_html(arxiv_id, cfg_lettura):
    r = scarica(f"https://arxiv.org/html/{arxiv_id}")
    if r.status_code != 200 or "ltx_document" not in r.text:
        return None
    s = BeautifulSoup(r.text, "lxml")

    abstract = s.select_one("div.ltx_abstract")
    abstract = " ".join(abstract.get_text(" ").split()) if abstract else ""
    abstract = re.sub(r"^Abstract\s*", "", abstract)

    didascalie = []
    for fc in s.select("figcaption"):
        if fc.find_parent(class_="ltx_appendix"):
            continue
        t = " ".join(fc.get_text(" ").split())
        if len(t) > 40:
            didascalie.append(t)
    didascalie = didascalie[: cfg_lettura["didascalie_max"]]

    sezioni, saltate = [], []
    for sec in s.select("section.ltx_section"):
        if sec.find_parent(class_="ltx_appendix"):
            continue
        h = sec.find(["h2", "h3"])
        titolo = " ".join(h.get_text(" ").split()) if h else "Sezione"
        titolo = re.sub(r"^\d+(\.\d+)*\s*", "", titolo)
        if SALTA.search(titolo):
            saltate.append(titolo)
            continue
        peso = next((w for rx, w in PESI if rx.search(titolo)), 0.6)
        testo = _testo(_pulisci_nodo(sec))
        if not testo:
            continue
        sezioni.append({"titolo": titolo,
                        "testo": _taglia(testo, int(cfg_lettura["parole_max_sezione"] * peso))})
    if not sezioni:
        return None
    return {"fonte": "arxiv-html", "abstract": abstract, "sezioni": sezioni,
            "didascalie": didascalie, "saltate": saltate}


def leggi_pdf(arxiv_id, cfg_lettura):
    import fitz  # PyMuPDF
    r = scarica(f"https://arxiv.org/pdf/{arxiv_id}", timeout=120)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    doc = fitz.open(stream=r.content, filetype="pdf")
    testo = "\n".join(p.get_text() for p in doc)
    # Si taglia alla bibliografia: dopo c'è solo zavorra.
    m = re.search(r"\n\s*(References|Bibliography|REFERENCES)\s*\n", testo)
    if m:
        testo = testo[: m.start()]
    testo = re.sub(r"-\n(\w)", r"\1", testo)
    testo = re.sub(r"\s*\n\s*", " ", testo)
    parole = testo.split()
    limite = cfg_lettura["parole_max_sezione"] * 4
    blocco = " ".join(parole[:limite])
    pezzi = [blocco[i:i + 12000] for i in range(0, len(blocco), 12000)]
    return {"fonte": "arxiv-pdf", "abstract": "",
            "sezioni": [{"titolo": f"Parte {i + 1}", "testo": p} for i, p in enumerate(pezzi)],
            "didascalie": [], "saltate": ["(PDF: sezioni non distinguibili)"]}


def leggi_paper(arxiv_id, cfg_lettura):
    return leggi_html(arxiv_id, cfg_lettura) or leggi_pdf(arxiv_id, cfg_lettura)


def a_pezzi(lettura, parole_per_pezzo):
    """Divide le sezioni in pezzi digeribili dal modello, a confine di paragrafo."""
    pezzi = []
    for sez in lettura["sezioni"]:
        corrente, n = [], 0
        for par in sez["testo"].split("\n\n"):
            k = len(par.split())
            if corrente and n + k > parole_per_pezzo:
                pezzi.append({"sezione": sez["titolo"], "testo": "\n\n".join(corrente)})
                corrente, n = [], 0
            corrente.append(par)
            n += k
        if corrente:
            pezzi.append({"sezione": sez["titolo"], "testo": "\n\n".join(corrente)})
    if lettura["didascalie"]:
        pezzi.append({"sezione": "Didascalie di figure e tabelle",
                      "testo": "\n\n".join(lettura["didascalie"])})
    return pezzi

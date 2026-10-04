"""Passi 3-6: scheda dei fatti, dialogo, controlli, titolo, descrizione, articolo."""
import html
import re

from . import controlli
from .util import conta_parole, prompt

# ---------------------------------------------------------------------
#  Schemi JSON: obbligano il modello a rispondere con questi campi.
# ---------------------------------------------------------------------

LISTA_TESTI = {"type": "array", "items": {"type": "string"}}

SCHEMA_ESTRAI = {
    "type": "object",
    "properties": {
        "fatti": LISTA_TESTI,
        "numeri": {"type": "array", "items": {"type": "object", "properties": {
            "valore": {"type": "string"}, "cosa_misura": {"type": "string"}},
            "required": ["valore", "cosa_misura"]}},
        "esempi": LISTA_TESTI,
        "limiti": LISTA_TESTI,
        "termini": LISTA_TESTI,
    },
    "required": ["fatti", "numeri", "esempi", "limiti", "termini"],
}

SCHEMA_SCHEDA = {
    "type": "object",
    "properties": {
        "nome_breve": {"type": "string"},
        "problema": {"type": "string"},
        "idea": {"type": "string"},
        "come_funziona": LISTA_TESTI,
        "risultati": {"type": "array", "items": {"type": "object", "properties": {
            "fatto": {"type": "string"}, "numero": {"type": "string"}, "scala": {"type": "string"},
            "in_pratica": {"type": "string"}},
            "required": ["fatto", "numero", "scala", "in_pratica"]}},
        "limiti": LISTA_TESTI,
        "esempio_concreto": {"type": "string"},
        "perche_ti_riguarda": {"type": "string"},
        "gancio": {"type": "string"},
        "termini": {"type": "array", "items": {"type": "object", "properties": {
            "termine": {"type": "string"},
            "tipo": {"type": "string", "enum": ["nome", "sigla", "tecnico"]},
            "espansione_inglese": {"type": "string"},
            "significato": {"type": "string"},
            "spiegazione": {"type": "string"},
            "usa": {"type": "string", "enum": ["termine", "spiegazione"]},
            "pronuncia": {"type": "string"}},
            "required": ["termine", "tipo", "espansione_inglese", "significato", "spiegazione", "usa", "pronuncia"]}},
        "soggetto_immagine": {"type": "string"},
        "hashtag": LISTA_TESTI,
    },
    "required": ["nome_breve", "problema", "idea", "come_funziona", "risultati", "limiti",
                 "esempio_concreto", "perche_ti_riguarda", "gancio", "termini",
                 "soggetto_immagine", "hashtag"],
}

SCHEMA_BLOCCO = {
    "type": "object",
    "properties": {"battute": {"type": "array", "items": {"type": "object", "properties": {
        "numero": {"type": "integer"}, "testo": {"type": "string"}},
        "required": ["numero", "testo"]}}},
    "required": ["battute"],
}

SCHEMA_TITOLO = {
    "type": "object",
    "properties": {"nome": {"type": "string"}, "sottotitolo": {"type": "string"}},
    "required": ["nome", "sottotitolo"],
}


# ---------------------------------------------------------------------
#  Passo 3: scheda dei fatti
# ---------------------------------------------------------------------

def estrai_pezzo(llm, lingua, paper, pezzo, cfg_m):
    s, u = prompt(lingua, "estrai", titolo=paper["titolo"], sezione=pezzo["sezione"],
                  testo=pezzo["testo"])
    return llm.chat(s, u, f"estrai: {pezzo['sezione'][:30]}", schema=SCHEMA_ESTRAI,
                    temperatura=cfg_m["temperatura_fatti"], max_token=1500)


def scheda(llm, lingua, paper, lettura, estratti, cfg_m):
    s, u = prompt(lingua, "scheda", titolo=paper["titolo"], abstract=lettura["abstract"] or paper["abstract"],
                  estratti=estratti)
    return llm.chat(s, u, "scheda", schema=SCHEMA_SCHEDA,
                    temperatura=cfg_m["temperatura_fatti"], max_token=3000)


# ---------------------------------------------------------------------
#  Passi 4-5: dialogo e correzioni
# ---------------------------------------------------------------------

def _regole_vietate(lingua):
    return "\n".join(f"- {v['esempio']}" for v in lingua["vietate"])


def scrivi_dialogo(llm, lingua, sk, numero, cfg_d, cfg_m):
    massimo = int(cfg_d["secondi_max"] / 60 * cfg_d["parole_al_minuto"])
    s, u = prompt(lingua, "dialogo", scheda=sk, numero=str(numero),
                  parole_obiettivo=str(massimo - 60), parole_max=str(massimo),
                  numeri_max=str(cfg_d.get("numeri_max", 4)),
                  vietate=_regole_vietate(lingua), **lingua["dialogo_vars"])
    for tentativo in range(3):
        testo = llm.chat(s, u, "dialogo", temperatura=cfg_m["temperatura_scrittura"], max_token=3000)
        if not llm.troncato:
            break
        # Dialogo tagliato a metà: si ricomincia, ricordando il limite.
        u += f"\n\nIMPORTANTE: il tentativo precedente era troppo lungo ed è stato interrotto. Resta sotto {massimo} parole."
    return controlli.analizza(testo, lingua)


def correggi_dialogo(llm, lingua, battute, sk, numero, cfg_d, cfg_m, avanz):
    """Cicla: controlla, sistema, ricontrolla. Ritorna battute e problemi residui."""
    for giro in range(1, cfg_d["giri_correzione"] + 1):
        per_b, glob, parole, massimo = controlli.controlla(battute, sk, lingua, cfg_d, numero)
        if not per_b and not glob:
            avanz.scrivi(f"   giro {giro}: nessun problema ({parole} parole, massimo {massimo})")
            return battute, []
        avanz.scrivi(f"   giro {giro}: {len(per_b)} battute da sistemare, "
                     f"{len(glob)} problemi generali ({parole} parole)")

        strutturali = [g for g in glob if g[0] == "struttura"]
        if strutturali:
            motivi = "\n".join(f"- {g[1]}" for g in strutturali)
            s, u = prompt(lingua, "struttura", dialogo=controlli.componi_tecnico(battute),
                          problemi=motivi, scheda=sk, numero=str(numero),
                          parole_obiettivo=str(massimo - 60), parole_max=str(massimo),
                          vietate=_regole_vietate(lingua), **lingua["dialogo_vars"])
            nuovo = controlli.analizza(llm.chat(s, u, "struttura", max_token=3000), lingua)
            if len(nuovo) >= 6:
                battute = nuovo
            continue

        # Lunghezza molto fuori misura: prima si sistema quella, perché
        # riscrivere battute che poi verranno tagliate è tempo perso.
        lung = [g for g in glob if g[0] == "lunghezza"]
        if lung and (parole > massimo * 1.25 or parole < cfg_d["parole_min"] * 0.75):
            _, motivo, obiettivo = lung[0]
            s, u = prompt(lingua, "lunghezza", dialogo=controlli.componi_tecnico(battute),
                          problema=motivo, parole_obiettivo=str(obiettivo), scheda=sk,
                          **lingua["dialogo_vars"])
            nuovo = controlli.analizza(llm.chat(s, u, "lunghezza", max_token=3000), lingua)
            if len(nuovo) >= 6:
                battute = nuovo
            continue

        if cfg_d.get("correzione_in_blocco") and per_b:
            battute = _riscrivi_in_blocco(llm, lingua, battute, per_b, sk)
        for i, motivi in ([] if cfg_d.get("correzione_in_blocco") else sorted(per_b.items())):
            if i >= len(battute):
                continue
            chi, b = battute[i]
            prima = battute[i - 1][1] if i > 0 else ""
            dopo = battute[i + 1][1] if i + 1 < len(battute) else ""
            s, u = prompt(lingua, "riscrivi", battuta=b, prima=prima, dopo=dopo,
                          chi=lingua["conduttori"][chi], problemi="\n".join(f"- {m}" for m in motivi),
                          scheda=sk)
            nuova = llm.chat(s, u, "riscrivi", temperatura=0.5, max_token=400)
            nuova = nuova.strip().splitlines()[0] if nuova.strip() else ""
            nomi = "|".join(map(re.escape, lingua["conduttori"].values()))
            nuova = re.sub(rf"^[\s*]*({nomi})[\s*]*:\s*", "", nuova, flags=re.I).strip()
            if nuova:
                battute[i] = (chi, nuova)

        lung = [g for g in glob if g[0] == "lunghezza"]
        if lung:
            _, motivo, obiettivo = lung[0]
            s, u = prompt(lingua, "lunghezza", dialogo=controlli.componi_tecnico(battute),
                          problema=motivo, parole_obiettivo=str(obiettivo), scheda=sk,
                          **lingua["dialogo_vars"])
            nuovo = controlli.analizza(llm.chat(s, u, "lunghezza", max_token=3000), lingua)
            if len(nuovo) >= 6:
                battute = nuovo

    per_b, glob, parole, massimo = controlli.controlla(battute, sk, lingua, cfg_d, numero)
    residui = [f"battuta {i + 1}: {'; '.join(m)}" for i, m in per_b.items()] + [g[1] for g in glob]
    return battute, residui


def _riscrivi_in_blocco(llm, lingua, battute, per_b, sk):
    """Una sola richiesta per tutte le battute da correggere.

    Serve con i servizi cloud, dove ogni richiesta conta nella quota
    giornaliera. Con i modelli locali si corregge una battuta alla volta.
    """
    nomi = lingua["conduttori"]
    dialogo = "\n".join(f"{i + 1}. {nomi[chi]}: {b}" for i, (chi, b) in enumerate(battute))
    elenco = "\n".join(f"- battuta {i + 1}: " + "; ".join(m) for i, m in sorted(per_b.items()))
    s, u = prompt(lingua, "riscrivi_blocco", dialogo=dialogo, problemi=elenco, scheda=sk)
    r = llm.chat(s, u, "riscrivi in blocco", schema=SCHEMA_BLOCCO, temperatura=0.5, max_token=3000)
    nuove = list(battute)
    for voce in r.get("battute", []):
        i = int(voce.get("numero", 0)) - 1
        testo = " ".join(str(voce.get("testo", "")).split())
        testo = re.sub(rf"^[\s*]*({'|'.join(map(re.escape, nomi.values()))})[\s*]*:\s*", "", testo, flags=re.I)
        if 0 <= i < len(nuove) and testo:
            nuove[i] = (nuove[i][0], testo)
    return nuove


# ---------------------------------------------------------------------
#  Passo 6: titolo, descrizione, articolo
# ---------------------------------------------------------------------

def titolo(llm, lingua, sk, paper, numero):
    s, u = prompt(lingua, "titolo", scheda=sk, titolo_originale=paper["titolo"])
    t = llm.chat(s, u, "titolo", schema=SCHEMA_TITOLO, temperatura=0.5, max_token=300)
    nome = t["nome"].strip().strip('"«»')
    sotto = t["sottotitolo"].strip().strip('"«»').rstrip(".")
    if len(sotto) > 1 and sotto[1].islower():   # "Quando..." -> "quando...", ma "AI ..." resta
        sotto = sotto[0].lower() + sotto[1:]
    if len(nome) > 40 and sk.get("nome_breve"):   # il modello ha scritto una frase al posto del nome
        nome = sk["nome_breve"].strip()
    completo = f"{lingua['nome_podcast']} #{numero} - {nome}: {sotto}"
    return {"nome": nome, "sottotitolo": sotto, "completo": completo}


def _autori(lista, L):
    if not lista:
        return ""
    if len(lista) > L["autori_max"]:
        return ", ".join(lista[:3]) + " " + L["e_altri"].format(n=len(lista) - 3)
    if len(lista) == 1:
        return lista[0]
    return ", ".join(lista[:-1]) + f" {L['e']} " + lista[-1]


def _hashtag(lista):
    out = []
    for h in lista:
        h = re.sub(r"[^\w]", "", h.replace("#", ""))
        if h and h.lower() not in {x.lower() for x in out}:
            out.append(h)
    return " ".join("#" + h for h in out[:6])


def descrizione(llm, lingua, sk, paper, meta, link, cloud=False):
    s, u = prompt(lingua, "descrizione", scheda=sk, titolo_originale=paper["titolo"],
                  vietate=_regole_vietate(lingua))
    corpo = llm.chat(s, u, "descrizione", temperatura=0.6, max_token=1200)
    corpo = correggi(llm, lingua, corpo)
    L = lingua["piede"]
    righe = [corpo.strip(), ""]
    autori = _autori(meta.get("autori") or paper["autori"], L)
    pag, fig = meta.get("pagine"), meta.get("figure")
    frase = L["autori"].format(autori=autori) if autori else ""
    if pag and fig:
        frase += L["pagine_figure"].format(p=pag, f=fig)
    elif pag:
        frase += L["solo_pagine"].format(p=pag)
    if frase:
        righe += [frase.strip() + ".", ""]
    firma = L["firma"] + " " + L.get("firma_cloud" if cloud else "firma_locale", "")
    righe += [L["link"].format(link=link), "", firma.strip(), "", _hashtag(sk.get("hashtag", []))]
    return "\n".join(righe).strip()


def articolo(llm, lingua, sk, paper, meta, link, cfg_a, avanz):
    s, u = prompt(lingua, "articolo", scheda=sk, titolo_originale=paper["titolo"],
                  parole_min=str(cfg_a["parole_min"]), parole_max=str(cfg_a["parole_max"]),
                  vietate=_regole_vietate(lingua))
    testo = llm.chat(s, u, "articolo", temperatura=0.6, max_token=3000)
    n = conta_parole(testo)
    if n < cfg_a["parole_min"] * 0.85 or n > cfg_a["parole_max"] * 1.15:
        avanz.avviso(f"articolo di {n} parole (atteso {cfg_a['parole_min']}-{cfg_a['parole_max']})")
    testo = correggi(llm, lingua, testo)
    L = lingua["piede"]
    autori = _autori(meta.get("autori") or paper["autori"], L)
    corpo_html = md_a_html(testo)
    piede = (f'<hr>\n<p><strong>{html.escape(L["paper"])}</strong> '
             f'<a href="{link}" target="_blank" rel="noopener">{html.escape(paper["titolo"])}</a>'
             + (f" — {html.escape(autori)}" if autori else "") + "</p>\n"
             f'<p>{html.escape(L["ascolta"])} <a href="{cfg_a["link_podcast"]}" target="_blank" '
             f'rel="noopener">{html.escape(lingua["nome_podcast"])}</a></p>')
    estratto = " ".join(re.split(r"(?<=[.!?])\s+", _primo_paragrafo(testo))[:2])
    return {"html": corpo_html + "\n" + piede, "markdown": testo, "estratto": estratto, "parole": n}


def correggi(llm, lingua, testo):
    """Corregge solo refusi. Se il modello cambia troppo, tiene l'originale."""
    s, u = prompt(lingua, "correggi", testo=testo)
    nuovo = llm.chat(s, u, "correggi", temperatura=0.0, max_token=3500)
    a, b = conta_parole(testo), conta_parole(nuovo)
    if not nuovo or abs(a - b) > max(5, a * 0.05):
        return testo
    return nuovo


def _primo_paragrafo(md):
    for p in md.split("\n\n"):
        p = p.strip()
        if p and not p.startswith("#") and not p.startswith("-"):
            return p
    return ""


def md_a_html(md):
    """Converte il markdown semplice del modello in HTML per WordPress."""
    def inline(t):
        t = html.escape(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", t)
        return t

    out, lista = [], []

    def chiudi_lista():
        if lista:
            out.append("<ul>\n" + "\n".join(f"<li>{inline(x)}</li>" for x in lista) + "\n</ul>")
            lista.clear()

    for blocco in re.split(r"\n\s*\n", md.strip()):
        righe = [r.strip() for r in blocco.strip().splitlines() if r.strip()]
        if not righe:
            continue
        if righe[0].startswith("#"):
            chiudi_lista()
            livello = min(max(len(righe[0]) - len(righe[0].lstrip("#")), 2), 3)
            out.append(f"<h{livello}>{inline(righe[0].lstrip('#').strip())}</h{livello}>")
            righe = righe[1:]
            if not righe:
                continue
        if all(re.match(r"^[-*•]\s+", r) for r in righe):
            lista.extend(re.sub(r"^[-*•]\s+", "", r) for r in righe)
            continue
        chiudi_lista()
        out.append(f"<p>{inline(' '.join(righe))}</p>")
    chiudi_lista()
    return "\n".join(out)

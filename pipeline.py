#!/usr/bin/env python3
"""AI Paper in Pillole - la catena notturna.

Uso:
  python pipeline.py                 notte normale, motori locali
  python pipeline.py --cloud         notte normale, motori cloud (Gemini), per GitHub Actions
  python pipeline.py --prova         cartella e registro di prova separati
  python pipeline.py --finto         senza modelli: collauda solo il flusso
  python pipeline.py --paper 2610.01762   forza un paper preciso
  python pipeline.py --rifai         ignora il lavoro già fatto oggi e ricomincia
  python pipeline.py --prova --modello gemma4:e4b   prova un altro modello locale

Ogni passo salva il suo risultato. Se qualcosa si rompe, rilanciando
il programma riparte dal passo interrotto.
"""
import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path

import yaml

from kit import audio, controlli, copertina, fonti, testi, voce
from kit.avvisi import Avanzamento
from kit.gpu import ContatoreVRAM
from kit.llm import Finto, Ollama
from kit.registro import Registro
from kit.uscita import archivia_se_vecchia, cartelle
from kit.util import (RADICE, carica_config, carica_lingua, conta_parole, leggi_json,
                      scrivi_json, scrivi_testo, slug)

P_SCELTA = "Scelta e lettura del paper"
P_SCHEDA = "Scheda dei fatti"
P_DIALOGO = "Dialogo"
P_CONTROLLI = "Controlli e correzioni"
P_TESTI = "Titolo, descrizione, articolo"
P_COPERTINA = "Copertina"
P_VOCE = "Voce"
P_MONTAGGIO = "Montaggio audio"
P_WP = "Articolo su WordPress"
P_CONSEGNA = "Consegna su Telegram"
P_REGISTRO = "Registro e chiusura"


def nomi_passi(lingue):
    def per(lista):
        return lista if len(lingue) == 1 else [f"{p} [{l}]" for l in lingue for p in lista]
    return ([P_SCELTA] + per([P_SCHEDA, P_DIALOGO, P_CONTROLLI, P_TESTI]) + [P_COPERTINA]
            + per([P_VOCE, P_MONTAGGIO, P_WP]) + [P_CONSEGNA, P_REGISTRO])


def nome_passo(p, lingua, lingue):
    return p if len(lingue) == 1 else f"{p} [{lingua}]"


# ---------------------------------------------------------------------
#  Passi 1-2: scelta e lettura
# ---------------------------------------------------------------------

def scegli_e_leggi(cfg, args, oggi, reg, lav, avanz):
    p_paper, p_lett = lav / "paper.json", lav / "lettura.json"
    if p_paper.exists() and p_lett.exists():
        paper = leggi_json(p_paper)
        avanz.saltato(P_SCELTA, f"{paper['arxiv_id']} (ripreso)")
        return paper, leggi_json(p_lett)

    avanz.inizia(P_SCELTA, "lettura della lista di Hugging Face")
    if args.paper:
        meta = fonti.metadati_arxiv(args.paper)
        if not meta:
            raise RuntimeError(f"arXiv non conosce il paper {args.paper}")
        cand = [{"arxiv_id": args.paper, "titolo": meta["titolo"], "voti": 0,
                 "abstract": meta["abstract"], "autori": meta["autori"], "lista_del": "manuale"}]
    else:
        cand, liste = fonti.candidati(cfg["scelta"], oggi)
        avanz.scrivi("   liste trovate: " + ", ".join(f"{d} ({n} paper)" for d, n in liste))
        if not cand:
            raise RuntimeError("Nessuna lista di Hugging Face negli ultimi giorni.")

    esclusi = reg.esclusi(cfg["lingue"][0])
    for c in cand:
        if c["arxiv_id"] in esclusi and not args.paper:
            continue
        avanz.scrivi(f"   provo {c['arxiv_id']} ({c['voti']} voti, lista del {c['lista_del']}): {c['titolo'][:70]}")
        lettura = fonti.leggi_paper(c["arxiv_id"], cfg["lettura"])
        if not lettura:
            avanz.avviso(f"{c['arxiv_id']} illeggibile (né HTML né PDF): scartato, passo al successivo")
            reg.scarta(c["arxiv_id"], "illeggibile")
            continue
        meta = fonti.metadati_arxiv(c["arxiv_id"])
        c["autori_arxiv"] = meta.get("autori") or c["autori"]
        c["pagine"], c["figure"] = fonti.pagine_figure(meta.get("commento", ""))
        c["link"] = f"https://arxiv.org/abs/{c['arxiv_id']}"
        if cand[0]["arxiv_id"] != c["arxiv_id"] and not args.paper:
            avanz.scrivi("   (i paper più votati erano già stati usati)")
        scrivi_json(p_lett, lettura)
        scrivi_json(p_paper, c)
        parole = sum(len(s["testo"].split()) for s in lettura["sezioni"])
        avanz.fatto(P_SCELTA, f"{c['arxiv_id']} · {c['voti']} voti · {lettura['fonte']} · {parole} parole utili")
        return c, lettura
    raise RuntimeError("Tutti i paper candidati sono già usati o illeggibili.")


# ---------------------------------------------------------------------
#  Passi 3-6 per una lingua: i testi
# ---------------------------------------------------------------------

def testi_lingua(L, cfg, cfg_m, paper, lettura, numero, llm, out, lav, lingue, avanz):
    cod = L["codice"]
    lav.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    cfg_d = cfg["dialogo"]
    meta = {"autori": paper.get("autori_arxiv"), "pagine": paper.get("pagine"), "figure": paper.get("figure")}

    # --- Passo 3: scheda dei fatti ---
    p = nome_passo(P_SCHEDA, cod, lingue)
    p_scheda = lav / "scheda.json"
    if p_scheda.exists():
        sk = leggi_json(p_scheda)
        avanz.saltato(p)
    else:
        pezzi = fonti.a_pezzi(lettura, cfg["lettura"]["parole_per_pezzo"],
                              cfg["lettura"].get("unisci_sezioni", False))
        p_estr = lav / "estratti.json"
        estratti = leggi_json(p_estr) if p_estr.exists() else []
        avanz.inizia(p, f"{len(pezzi)} pezzi da leggere")
        for i, pezzo in enumerate(pezzi[len(estratti):], start=len(estratti) + 1):
            avanz.inizia(p, f"pezzo {i} di {len(pezzi)}: {pezzo['sezione'][:40]}")
            e = testi.estrai_pezzo(llm, L, paper, pezzo, cfg_m)
            estratti.append({"parte": pezzo["sezione"], **e})
            scrivi_json(p_estr, estratti)
        avanz.inizia(p, "unione dei fatti nella scheda")
        sk = testi.scheda(llm, L, paper, lettura, estratti, cfg_m)
        scrivi_json(p_scheda, sk)
        avanz.fatto(p, f"{sk.get('nome_breve', '')} · {len(sk.get('risultati', []))} risultati · "
                       f"{len(sk.get('termini', []))} termini")

    # --- Passo 4: dialogo ---
    p = nome_passo(P_DIALOGO, cod, lingue)
    p_bozza = lav / "dialogo_bozza.txt"
    if p_bozza.exists():
        battute = controlli.analizza(p_bozza.read_text(encoding="utf-8"), L)
        avanz.saltato(p)
    else:
        avanz.inizia(p, f"puntata #{numero}")
        battute = testi.scrivi_dialogo(llm, L, sk, numero, cfg_d, cfg_m)
        if len(battute) < 6:
            battute = testi.scrivi_dialogo(llm, L, sk, numero, cfg_d, cfg_m)
        if len(battute) < 6:
            raise RuntimeError("Il modello non ha prodotto un dialogo nel formato CARLO:/ARIANNA:")
        scrivi_testo(p_bozza, controlli.componi_tecnico(battute))
        avanz.fatto(p, f"{len(battute)} battute, {sum(conta_parole(b) for _, b in battute)} parole")

    # --- Passo 5: controlli e correzioni ---
    p = nome_passo(P_CONTROLLI, cod, lingue)
    p_finale = lav / "dialogo_finale.txt"
    if p_finale.exists():
        battute = controlli.analizza(p_finale.read_text(encoding="utf-8"), L)
        avanz.saltato(p)
    else:
        avanz.inizia(p)
        battute, residui = testi.correggi_dialogo(llm, L, battute, sk, numero, cfg_d, cfg_m, avanz)
        for r in residui:
            avanz.avviso(f"[{cod}] dialogo, {r}")
        scrivi_testo(p_finale, controlli.componi_tecnico(battute))
        avanz.fatto(p, "nessun problema residuo" if not residui else f"{len(residui)} problemi residui")

    if L.get("decimali_virgola"):
        # 72.1 → 72,1 (solo decimali di 1-2 cifre: 4.560 resta un "migliaia")
        # Non si toccano i nomi con numeri di versione (Qwen3.6, GLM-5.2): lettera o
        # trattino attaccati al numero.
        battute = [(chi, re.sub(r"(?<![\w.,-])0\.(\d+)(?![\w-])", r"0,\1",
                                re.sub(r"(?<![\w.,-])(\d+)\.(\d{1,2})(?![\w-])", r"\1,\2", b)))
                   for chi, b in battute]
    parole = sum(conta_parole(b) for _, b in battute)
    dialogo_txt = controlli.componi(battute, L)
    if L.get("frase_finale"):
        dialogo_txt += f"\n\n[dopo la sigla] {L['conduttori'][L['frase_finale'].get('chi', 'ARIANNA')]}: {L['frase_finale']['testo']}"
    scrivi_testo(out / "dialogo.txt", dialogo_txt)
    proposte = {}
    battute_voce = battute
    if L.get("pronuncia_attiva"):
        mappa, proposte = controlli.mappa_pronuncia(L, sk)
        battute_voce = controlli.versione_voce(battute, mappa)
    scrivi_testo(lav / "dialogo_voce.txt", controlli.componi_tecnico(battute_voce))

    # --- Passo 6: titolo, descrizione, articolo ---
    p = nome_passo(P_TESTI, cod, lingue)
    p_tit = lav / "titolo.json"
    if p_tit.exists() and (out / "articolo.html").exists():
        tit = leggi_json(p_tit)
        avanz.saltato(p)
    else:
        avanz.inizia(p, "titolo")
        tit = testi.titolo(llm, L, sk, paper, numero)
        scrivi_json(p_tit, tit)
        avanz.inizia(p, "descrizione")
        desc = testi.descrizione(llm, L, sk, paper, meta, paper["link"],
                                 cloud=cfg["motori"]["testo"] == "gemini")
        scrivi_testo(lav / "descrizione.txt", desc)
        # Titolo e descrizione in un unico file: titolo, riga vuota, descrizione.
        scrivi_testo(out / "titolo_e_descrizione.txt", f"{tit['completo']}\n\n{desc}")
        avanz.inizia(p, "articolo per il sito")
        art = testi.articolo(llm, L, sk, paper, meta, paper["link"], cfg["articolo"], avanz)
        scrivi_testo(out / "articolo.html", art["html"])
        scrivi_json(lav / "articolo_meta.json", {
            "titolo": f"{tit['nome']}: {tit['sottotitolo']}",
            "estratto": art["estratto"], "tag": sk.get("hashtag", []),
            "categoria": cfg["wordpress"]["categoria"], "parole": art["parole"]})
        avanz.fatto(p, f"«{tit['completo'][:60]}» · articolo {art['parole']} parole")

    return {"titolo": tit, "parole": parole, "proposte": proposte, "scheda": sk,
            "battute": battute, "battute_voce": battute_voce}


# ---------------------------------------------------------------------
#  Passi 7, 9, 10 per una lingua: voce, montaggio, WordPress
# ---------------------------------------------------------------------

def audio_e_sito(L, cfg, motore_voce, esito, paper, out, lav, lingue, avanz, finto):
    cod = L["codice"]
    cfg_d, cfg_a = cfg["dialogo"], cfg["audio"]

    # --- Passo 7: voce ---
    p_voce = nome_passo(P_VOCE, cod, lingue)
    p_mont = nome_passo(P_MONTAGGIO, cod, lingue)
    if motore_voce is None:
        avanz.saltato(p_voce, "motore voce: nessuno")
        avanz.saltato(p_mont, "niente voce, niente montaggio")
    else:
        # Le voci cloud leggono bene i nomi inglesi: ricevono il testo normale.
        battute = esito["battute"] if cfg["motori"]["voce"] == "gemini" else esito["battute_voce"]
        avanz.inizia(p_voce)
        per_blocco = cfg["gemini_voce"].get("battute_per_blocco", 14)
        g, c = voce.genera(motore_voce, battute, L, lav / "voce", per_blocco, avanz, p_voce)
        firma = voce.genera_firma(motore_voce, L, lav / "voce", avanz, p_voce)
        avanz.fatto(p_voce, f"{len(g) + len(c)} blocchi" + (" + frase finale" if firma else ""))

        # --- Passo 9: montaggio ---
        if (out / "puntata.wav").exists() and (out / "puntata.mp3").exists():
            avanz.saltato(p_mont)
        else:
            avanz.inizia(p_mont)
            ris = audio.monta(g, c, RADICE / cfg_a["sigla_apertura"], RADICE / cfg_a["sigla_chiusura"],
                              out / "puntata.wav", out / "puntata.mp3", cfg_a, firma=firma)
            scrivi_json(lav / "audio.json", ris)
            ritmo = esito["parole"] / max(ris["voce"] / 60, 0.1)
            avanz.fatto(p_mont, f"{ris['durata'] / 60:.1f} minuti in tutto, voce {ris['voce'] / 60:.1f} "
                                f"minuti, {ritmo:.0f} parole al minuto")
            if ris["voce"] > cfg_d["secondi_max"] + 30:
                avanz.avviso(f"[{cod}] la voce dura {ris['voce'] / 60:.1f} minuti, oltre il limite di "
                             f"{cfg_d['secondi_max'] / 60:.1f}. In config.yaml abbassa parole_al_minuto "
                             f"a circa {ritmo:.0f}.")

    # --- Passo 10: WordPress ---
    p_wp = nome_passo(P_WP, cod, lingue)
    cfg_wp = cfg["wordpress"]
    p_esito = lav / "wordpress.json"
    if p_esito.exists():
        avanz.saltato(p_wp, leggi_json(p_esito).get("link", ""))
    elif finto:
        avanz.saltato(p_wp, "prova con motori finti: niente pubblicazione")
    elif not cfg_wp.get("attivo") or cod not in cfg_wp.get("lingue", ["it"]):
        avanz.saltato(p_wp, "non attivo per questa lingua")
    else:
        from kit.wordpress import ErroreWordPress, WordPress
        avanz.inizia(p_wp, f"stato: {cfg_wp['stato']}")
        meta = leggi_json(lav / "articolo_meta.json")
        try:
            wp = WordPress(cfg_wp["sito"])
            r = wp.pubblica(meta["titolo"], (out / "articolo.html").read_text(encoding="utf-8"),
                            meta["estratto"], meta["categoria"], meta["tag"], out / "copertina.jpg",
                            cfg_wp["stato"], paper["arxiv_id"], sostituisci=cfg.get("sostituisci", False))
            scrivi_json(p_esito, r)
            avanz.fatto(p_wp, ("già presente: " if r["esisteva"] else "") + f"{r['stato']} · {r.get('link', '')}")
        except ErroreWordPress as e:
            # Il sito non deve bloccare la puntata: si segnala e si va avanti.
            avanz.avviso(f"WordPress non raggiunto da questo server ({str(e)[:80]}): "
                         f"riprovo tra 15 minuti da un altro server (fino a 2 volte), l'esito arriva in un messaggio a parte")
            avanz.stati[p_wp] = ("errore", str(e)[:120])


# ---------------------------------------------------------------------

def consegna(cfg, lingue, oggi_dir, numero, avanz, lav):
    p_ok = lav / "consegnato.json"
    if p_ok.exists():
        avanz.saltato(P_CONSEGNA)
        return
    if not (cfg["telegram"].get("manda_file") and avanz.tg):
        avanz.saltato(P_CONSEGNA, "Telegram non attivo")
        return
    avanz.inizia(P_CONSEGNA)
    inviati = 0
    for cod in lingue:
        out = oggi_dir if len(lingue) == 1 else oggi_dir / cod
        pre = "" if len(lingue) == 1 else f"[{cod}] "
        # Titolo e descrizione anche come messaggi separati, comodi da copiare.
        lc = lav / cod
        if (lc / "titolo.json").exists():
            avanz.manda(leggi_json(lc / "titolo.json")["completo"])
        if (lc / "descrizione.txt").exists():
            avanz.manda((lc / "descrizione.txt").read_text(encoding="utf-8").strip())
        for nome, come, didascalia in (("titolo_e_descrizione.txt", "documento", "Titolo e descrizione"),
                                       ("copertina.jpg", "documento", "Copertina"),
                                       ("dialogo.txt", "documento", f"Dialogo della puntata #{numero}"),
                                       ("puntata.mp3", "audio", f"Puntata #{numero} (mp3, archivio)"),
                                       ("puntata.wav", "documento", f"Puntata #{numero} (wav, per Spotify)")):
            if (out / nome).exists() and avanz.manda_file(out / nome, pre + didascalia, come):
                inviati += 1
    scrivi_json(p_ok, {"file": inviati})
    avanz.fatto(P_CONSEGNA, f"{inviati} file inviati")


def archivia_in_git(cfg, lingue, oggi_dir, data, numero, nome_breve, avanz):
    """Nel cloud: copia testi, copertina e mp3 della puntata nel repository.
    Il wav (troppo pesante per il repository) va nelle Releases di GitHub."""
    if not cfg.get("archivio_git"):
        return
    dest = cfg["archivio_git"] / "puntate" / f"{data}_{numero:03d}_{slug(nome_breve)}"
    dest.mkdir(parents=True, exist_ok=True)
    for cod in lingue:
        out = oggi_dir if len(lingue) == 1 else oggi_dir / cod
        d = dest if len(lingue) == 1 else dest / cod
        d.mkdir(parents=True, exist_ok=True)
        for nome in ("titolo_e_descrizione.txt", "dialogo.txt", "articolo.html", "copertina.jpg", "puntata.mp3"):
            if (out / nome).exists():
                shutil.copy2(out / nome, d / nome)
        for nome in ("scheda.json", "articolo_meta.json", "wordpress.json"):
            f = oggi_dir / ".lavoro" / cod / nome
            if f.exists():
                shutil.copy2(f, d / nome)
            elif nome == "wordpress.json" and cfg.get("sostituisci") and (d / nome).exists():
                (d / nome).unlink()   # l'articolo va ancora aggiornato: i tentativi successivi lo faranno
    if (oggi_dir / "registro.log").exists():
        shutil.copy2(oggi_dir / "registro.log", dest / "registro.log")
    avanz.scrivi(f"Testi archiviati nel repository: {dest.relative_to(RADICE)}")


def salva_proposte(cartella, cod, proposte):
    if not proposte:
        return
    p = Path(cartella) / f"pronunce_proposte_{cod}.yaml"
    esistenti = (yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}) or {}
    nuove = {k: v for k, v in proposte.items() if k not in esistenti}
    if nuove:
        esistenti.update(nuove)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# Pronunce proposte dal modello. Copia in lingue/" + cod +
                     "/pronuncia.yaml quelle giuste (correggendole se serve).\n" +
                     yaml.safe_dump(esistenti, allow_unicode=True, sort_keys=True), encoding="utf-8")


def crea_motore_testo(cfg, args, avanz, lingua0):
    if args.finto:
        return Finto(avanz, lingua0), cfg["modello_testo"]
    if cfg["motori"]["testo"] == "gemini":
        from kit.gemini import GeminiTesto
        return GeminiTesto(cfg["gemini_testo"], avanz), cfg["gemini_testo"]
    return Ollama(cfg["modello_testo"], avanz), cfg["modello_testo"]


def crea_motore_voce(cfg, args, L, avanz):
    if cfg["motori"]["voce"] == "nessuna":
        return None
    if args.finto:
        return voce.VoceFinta()
    if cfg["motori"]["voce"] == "gemini":
        from kit.gemini import GeminiVoce
        return GeminiVoce(cfg["gemini_voce"], L, avanz)
    raise RuntimeError(f"motore voce sconosciuto: {cfg['motori']['voce']}")


def main():
    ap = argparse.ArgumentParser(description="AI Paper in Pillole - catena notturna")
    ap.add_argument("--cloud", action="store_true", help="usa il profilo cloud di config.yaml (Gemini)")
    ap.add_argument("--prova", action="store_true", help="cartella e registro di prova separati")
    ap.add_argument("--finto", action="store_true", help="motori finti al posto dei modelli")
    ap.add_argument("--paper", help="forza un paper arXiv (es. 2610.01762)")
    ap.add_argument("--rifai", action="store_true", help="ricomincia il lavoro di oggi da capo")
    ap.add_argument("--data", help="finge che oggi sia questa data (AAAA-MM-GG)")
    ap.add_argument("--modello", help="usa un altro modello Ollama solo per questa volta (es. gemma4:e4b)")
    ap.add_argument("--voce", choices=["gemini", "nessuna"], help="sceglie il motore voce solo per questa volta")
    ap.add_argument("--sostituisci", action="store_true",
                    help="con --paper: rifà una puntata già uscita, con lo stesso numero, e aggiorna l'articolo")
    ap.add_argument("--se-manca", action="store_true",
                    help="esce subito se la puntata di oggi è già fatta (per le sveglie di riserva)")
    args = ap.parse_args()

    cfg = carica_config(cloud=args.cloud)
    if args.sostituisci and not args.paper:
        ap.error("--sostituisci serve insieme a --paper")
    cfg["sostituisci"] = args.sostituisci
    if args.modello:
        cfg["modello_testo"]["nome"] = args.modello
    if args.voce:
        cfg["motori"]["voce"] = args.voce
    if args.prova:
        cfg["cartella_base"] = Path(str(cfg["cartella_base"]) + "-PROVA")
        if cfg.get("archivio_git"):
            cfg["archivio_git"] = Path(str(cfg["archivio_git"]) + "-PROVA")
    oggi = dt.date.fromisoformat(args.data) if args.data else dt.date.today()
    data = oggi.isoformat()
    lingue = cfg["lingue"]

    if args.se_manca:
        db = (cfg["archivio_git"] if cfg.get("archivio_git") else Path(cfg["cartella_base"]) / "dati") / "registro.sqlite"
        if db.exists() and Registro(db).fatta_il(lingue[0], data):
            print(f"La puntata del {data} è già fatta: niente da fare.")
            return 0

    base, oggi_dir, old_dir = cartelle(cfg)
    if args.rifai and oggi_dir.exists():
        for f in oggi_dir.iterdir():
            shutil.rmtree(f) if f.is_dir() else f.unlink()
    archivia_se_vecchia(oggi_dir, old_dir, data, print)
    lav = oggi_dir / ".lavoro"
    lav.mkdir(exist_ok=True)
    dati_dir = cfg["archivio_git"] if cfg.get("archivio_git") else base / "dati"

    etichetta = " (PROVA)" if args.prova else ""
    etichetta += " · cloud" if args.cloud else ""
    avanz = Avanzamento(nomi_passi(lingue), oggi_dir / "registro.log",
                        telegram_attivo=cfg["telegram"]["attivo"] and not args.finto,
                        intestazione=f"🎙 AI Paper in Pillole — notte del {data}{etichetta}")
    vram = ContatoreVRAM().avvia()
    reg = Registro(dati_dir / "registro.sqlite")
    p_stato = lav / "stato.json"
    stato = leggi_json(p_stato) if p_stato.exists() else {"data": data, "completa": False}
    scrivi_json(p_stato, stato)  # subito: un errore precoce non deve far archiviare la giornata
    try:
        vram.fase = "lettura"
        paper, lettura = scegli_e_leggi(cfg, args, oggi, reg, lav, avanz)
        stato.setdefault("numeri", {})
        for cod in lingue:
            vecchio = reg.numero_di(paper["arxiv_id"], cod) if args.sostituisci else None
            if vecchio:
                stato["numeri"][cod] = vecchio
            stato["numeri"].setdefault(cod, reg.prossimo_numero(cod, cfg["numero_iniziale"].get(cod, 1)))
            if not vecchio:   # una puntata da sostituire resta "completa" anche se il rifacimento si ferma
                reg.segna(paper["arxiv_id"], cod, "in_lavorazione", data, stato["numeri"][cod],
                          paper["titolo"], paper["voti"])
        stato.update({"arxiv_id": paper["arxiv_id"], "numero": stato["numeri"][lingue[0]]})
        scrivi_json(p_stato, stato)

        # --- testi ---
        llm, cfg_m = crea_motore_testo(cfg, args, avanz, lingue[0])
        llm.controlla()
        vram.fase = "testo"
        lingua = {cod: carica_lingua(cod) for cod in lingue}
        esiti = {}
        for cod in lingue:
            out = oggi_dir if len(lingue) == 1 else oggi_dir / cod
            esiti[cod] = testi_lingua(lingua[cod], cfg, cfg_m, paper, lettura, stato["numeri"][cod],
                                      llm, out, lav / cod, lingue, avanz)
            if cod == lingue[0]:
                stato["nome_breve"] = esiti[cod]["titolo"]["nome"]
                scrivi_json(p_stato, stato)
        llm.libera()

        # --- copertina (una per paper, uguale per tutte le lingue) ---
        vram.fase = "immagine"
        sk0 = esiti[lingue[0]]["scheda"]
        prima = (oggi_dir if len(lingue) == 1 else oggi_dir / lingue[0]) / "copertina.jpg"
        if prima.exists():
            avanz.saltato(P_COPERTINA)
        else:
            avanz.inizia(P_COPERTINA)
            testi_tema = [sk0.get("soggetto_immagine"), paper["titolo"], " ".join(sk0.get("hashtag", []))]
            fatta = None
            if cfg["motori"]["copertina"] == "gemini" and not args.finto:
                try:
                    from kit.gemini import GeminiImmagine
                    dati = GeminiImmagine(cfg["gemini_immagine"], avanz).genera(
                        sk0.get("soggetto_immagine") or paper["titolo"])
                    copertina.salva_da_bytes(prima, dati, cfg["copertina"]["lato"])
                    fatta = "disegnata da Gemini"
                except Exception as e:
                    # La copertina non deve bloccare la puntata: si ripiega sul disegno del programma.
                    avanz.avviso(f"copertina Gemini non riuscita ({str(e)[:150]}): uso il disegno del programma")
            if not fatta:
                motivo = copertina.disegna(prima, paper["arxiv_id"], testi_tema, cfg["copertina"])
                fatta = f"disegno del programma, icona «{motivo}»"
            for cod in lingue[1:]:
                shutil.copy2(prima, oggi_dir / cod / "copertina.jpg")
            avanz.fatto(P_COPERTINA, fatta)

        # --- voce, montaggio, sito ---
        vram.fase = "voce"
        for cod in lingue:
            out = oggi_dir if len(lingue) == 1 else oggi_dir / cod
            motore_voce = crea_motore_voce(cfg, args, lingua[cod], avanz)
            audio_e_sito(lingua[cod], cfg, motore_voce, esiti[cod], paper, out, lav / cod,
                         lingue, avanz, args.finto)

        consegna(cfg, lingue, oggi_dir, stato["numero"], avanz, lav)

        # --- registro ---
        avanz.inizia(P_REGISTRO)
        for cod in lingue:
            reg.segna(paper["arxiv_id"], cod, "completa", data, stato["numeri"][cod],
                      esiti[cod]["titolo"]["completo"], paper["voti"])
            salva_proposte(dati_dir, cod, esiti[cod]["proposte"])
        stato["completa"] = True
        scrivi_json(p_stato, stato)
        richieste = getattr(llm, "richieste", None)
        if richieste is not None:
            avanz.scrivi(f"Richieste al modello di testo: {richieste}"
                         + (" (usata anche la chiave a pagamento)"
                            if getattr(getattr(llm, "chiavi", None), "usata_pagamento", False) else ""))
        vram.ferma()
        testo_vram, sfora = vram.rapporto(cfg["gpu"]["limite_vram_mb"])
        avanz.scrivi(testo_vram)
        if sfora and not args.cloud:
            avanz.avviso("la memoria video ha superato il limite della GTX 1070: " + testo_vram)
        archivia_in_git(cfg, lingue, oggi_dir, data, stato["numero"], stato.get("nome_breve", "puntata"), avanz)
        avanz.fatto(P_REGISTRO)

        e = esiti[lingue[0]]
        wp = lav / lingue[0] / "wordpress.json"
        riga_wp = ""
        if wp.exists():
            w = leggi_json(wp)
            riga_wp = f"\nArticolo: {'in bozza' if w.get('stato') == 'draft' else w.get('stato')} · {w.get('link', '')}"
        riepilogo = (f"Puntata #{stato['numero']} pronta.\n{e['titolo']['completo']}\n"
                     f"Dialogo: {e['parole']} parole.\nPaper: {paper['link']}{riga_wp}")
        avanz.fine(riepilogo)
        return 0
    except KeyboardInterrupt:
        avanz.scrivi("Interrotto a mano. Rilanciando, riprende da qui.")
        return 130
    except Exception as exc:
        avanz.errore(P_SCELTA, exc)
        return 1
    finally:
        vram.ferma()


if __name__ == "__main__":
    sys.exit(main())

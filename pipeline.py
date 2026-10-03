#!/usr/bin/env python3
"""AI Paper in Pillole - la catena notturna.

Uso:
  python pipeline.py                 notte normale
  python pipeline.py --prova         stessa cosa, ma in una cartella di prova separata
                                     (non tocca il registro vero)
  python pipeline.py --finto         senza modello: collauda solo il flusso
  python pipeline.py --paper 2610.01762   forza un paper preciso
  python pipeline.py --rifai         ignora il lavoro già fatto oggi e ricomincia
  python pipeline.py --prova --modello gemma4:e4b   prova un altro modello

Ogni passo salva il suo risultato. Se qualcosa si rompe, rilanciando
il programma riparte dal passo interrotto.
"""
import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

import yaml

from kit import controlli, fonti, testi
from kit.avvisi import Avanzamento
from kit.gpu import ContatoreVRAM
from kit.llm import Finto, Ollama
from kit.registro import Registro
from kit.uscita import archivia_se_vecchia, cartelle
from kit.util import (carica_config, carica_lingua, conta_parole, leggi_json,
                      scrivi_json, scrivi_testo)

P_SCELTA = "Scelta e lettura del paper"
P_SCHEDA = "Scheda dei fatti"
P_DIALOGO = "Dialogo"
P_CONTROLLI = "Controlli e correzioni"
P_TESTI = "Titolo, descrizione, articolo"
P_VOCE = "Voce"
P_COPERTINA = "Copertina"
P_MONTAGGIO = "Montaggio audio"
P_WP = "Articolo su WordPress"
P_REGISTRO = "Registro e chiusura"
NON_COSTRUITI = [P_VOCE, P_COPERTINA, P_MONTAGGIO, P_WP]


def nomi_passi(lingue):
    per_lingua = [P_SCHEDA, P_DIALOGO, P_CONTROLLI, P_TESTI]
    if len(lingue) == 1:
        centrali = per_lingua
    else:
        centrali = [f"{p} [{l}]" for l in lingue for p in per_lingua]
    return [P_SCELTA] + centrali + NON_COSTRUITI + [P_REGISTRO]


def nome_passo(p, lingua, lingue):
    return p if len(lingue) == 1 else f"{p} [{lingua}]"


# ---------------------------------------------------------------------
#  Passo 1-2
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
        if c["voti"] and cand[0]["arxiv_id"] != c["arxiv_id"]:
            avanz.scrivi("   (i paper più votati erano già stati usati)")
        scrivi_json(p_lett, lettura)
        scrivi_json(p_paper, c)
        parole = sum(len(s["testo"].split()) for s in lettura["sezioni"])
        avanz.fatto(P_SCELTA, f"{c['arxiv_id']} · {c['voti']} voti · {lettura['fonte']} · {parole} parole utili")
        return c, lettura
    raise RuntimeError("Tutti i paper candidati sono già usati o illeggibili.")


# ---------------------------------------------------------------------
#  Passi 3-6 per una lingua
# ---------------------------------------------------------------------

def lavora_lingua(cod, cfg, paper, lettura, numero, llm, out, lav, lingue, avanz):
    L = carica_lingua(cod)
    lav.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    cfg_m, cfg_d = cfg["modello_testo"], cfg["dialogo"]
    meta = {"autori": paper.get("autori_arxiv"), "pagine": paper.get("pagine"), "figure": paper.get("figure")}

    # --- Passo 3: scheda dei fatti ---
    p = nome_passo(P_SCHEDA, cod, lingue)
    p_scheda = lav / "scheda.json"
    if p_scheda.exists():
        sk = leggi_json(p_scheda)
        avanz.saltato(p)
    else:
        pezzi = fonti.a_pezzi(lettura, cfg["lettura"]["parole_per_pezzo"])
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

    parole = sum(conta_parole(b) for _, b in battute)
    durata = parole / cfg_d["parole_al_minuto"] * 60
    scrivi_testo(out / "dialogo.txt", controlli.componi(battute, L))
    proposte = {}
    if L.get("pronuncia_attiva"):
        mappa, proposte = controlli.mappa_pronuncia(L, sk)
        voce = controlli.versione_voce(battute, mappa)
    else:
        voce = battute
    scrivi_testo(lav / "dialogo_voce.txt", controlli.componi_tecnico(voce))

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
        scrivi_testo(out / "titolo.txt", tit["completo"])
        avanz.inizia(p, "descrizione")
        desc = testi.descrizione(llm, L, sk, paper, meta, paper["link"])
        scrivi_testo(out / "descrizione.txt", desc)
        avanz.inizia(p, "articolo per il sito")
        art = testi.articolo(llm, L, sk, paper, meta, paper["link"], cfg["articolo"], avanz)
        scrivi_testo(out / "articolo.html", art["html"])
        scrivi_json(lav / "articolo_meta.json", {
            "titolo": f"{tit['nome']}: {tit['sottotitolo']}",
            "estratto": art["estratto"], "tag": sk.get("hashtag", []),
            "categoria": cfg["wordpress"]["categoria"], "parole": art["parole"]})
        avanz.fatto(p, f"«{tit['completo'][:60]}» · articolo {art['parole']} parole")

    return {"titolo": tit, "parole": parole, "durata": durata, "proposte": proposte}


# ---------------------------------------------------------------------

def salva_proposte(base, cod, proposte):
    if not proposte:
        return
    p = base / "dati" / f"pronunce_proposte_{cod}.yaml"
    esistenti = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    esistenti = esistenti or {}
    nuove = {k: v for k, v in proposte.items() if k not in esistenti}
    if nuove:
        esistenti.update(nuove)
        p.write_text("# Pronunce proposte dal modello. Copia in lingue/" + cod +
                     "/pronuncia.yaml quelle giuste (correggendole se serve).\n" +
                     yaml.safe_dump(esistenti, allow_unicode=True, sort_keys=True), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="AI Paper in Pillole - catena notturna")
    ap.add_argument("--prova", action="store_true", help="cartella e registro di prova separati")
    ap.add_argument("--finto", action="store_true", help="motore finto al posto del modello")
    ap.add_argument("--paper", help="forza un paper arXiv (es. 2610.01762)")
    ap.add_argument("--rifai", action="store_true", help="ricomincia il lavoro di oggi da capo")
    ap.add_argument("--data", help="finge che oggi sia questa data (AAAA-MM-GG)")
    ap.add_argument("--modello", help="usa un altro modello Ollama solo per questa volta (es. gemma4:e4b)")
    args = ap.parse_args()

    cfg = carica_config()
    if args.modello:
        cfg["modello_testo"]["nome"] = args.modello
    if args.prova:
        cfg["cartella_base"] = Path(str(cfg["cartella_base"]) + "-PROVA")
    oggi = dt.date.fromisoformat(args.data) if args.data else dt.date.today()
    data = oggi.isoformat()
    lingue = cfg["lingue"]

    base, oggi_dir, old_dir = cartelle(cfg)
    if args.rifai and (oggi_dir / ".lavoro").exists():
        shutil.rmtree(oggi_dir / ".lavoro")
        for f in oggi_dir.iterdir():
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                shutil.rmtree(f)
    archivia_se_vecchia(oggi_dir, old_dir, data, print)
    lav = oggi_dir / ".lavoro"
    lav.mkdir(exist_ok=True)

    avanz = Avanzamento(nomi_passi(lingue), oggi_dir / "registro.log",
                        telegram_attivo=cfg["telegram"]["attivo"] and not args.finto,
                        intestazione=f"🎙 AI Paper in Pillole — notte del {data}"
                                     + (" (PROVA)" if args.prova else ""))
    vram = ContatoreVRAM().avvia()
    reg = Registro(base)
    p_stato = lav / "stato.json"
    stato = leggi_json(p_stato) if p_stato.exists() else {"data": data, "completa": False}
    scrivi_json(p_stato, stato)  # subito: un errore precoce non deve far archiviare la giornata
    passo = P_SCELTA
    try:
        vram.fase = "lettura"
        paper, lettura = scegli_e_leggi(cfg, args, oggi, reg, lav, avanz)
        stato.setdefault("numeri", {})
        for cod in lingue:
            stato["numeri"].setdefault(cod, reg.prossimo_numero(cod, cfg["numero_iniziale"].get(cod, 1)))
            reg.segna(paper["arxiv_id"], cod, "in_lavorazione", data, stato["numeri"][cod],
                      paper["titolo"], paper["voti"])
        stato.update({"arxiv_id": paper["arxiv_id"], "numero": stato["numeri"][lingue[0]]})
        scrivi_json(p_stato, stato)

        llm = Finto(avanz, lingue[0]) if args.finto else Ollama(cfg["modello_testo"], avanz)
        passo = P_SCHEDA
        llm.controlla()
        vram.fase = "testo"
        esiti = {}
        for cod in lingue:
            out = oggi_dir if len(lingue) == 1 else oggi_dir / cod
            passo = nome_passo(P_SCHEDA, cod, lingue)
            esiti[cod] = lavora_lingua(cod, cfg, paper, lettura, stato["numeri"][cod], llm,
                                       out, lav / cod, lingue, avanz)
            if cod == lingue[0]:
                stato["nome_breve"] = esiti[cod]["titolo"]["nome"]
                scrivi_json(p_stato, stato)
        llm.libera()

        for p in NON_COSTRUITI:
            avanz.saltato(p, "non ancora costruito")

        passo = P_REGISTRO
        avanz.inizia(passo)
        for cod in lingue:
            reg.segna(paper["arxiv_id"], cod, "completa", data, stato["numeri"][cod],
                      esiti[cod]["titolo"]["completo"], paper["voti"])
            salva_proposte(base, cod, esiti[cod]["proposte"])
        stato["completa"] = True
        scrivi_json(p_stato, stato)
        vram.ferma()
        testo_vram, sfora = vram.rapporto(cfg["gpu"]["limite_vram_mb"])
        avanz.scrivi(testo_vram)
        if sfora:
            avanz.avviso("la memoria video ha superato il limite della GTX 1070: " + testo_vram)
        avanz.fatto(passo)

        e = esiti[lingue[0]]
        riepilogo = (f"Puntata #{stato['numero']} pronta.\n{e['titolo']['completo']}\n"
                     f"Dialogo: {e['parole']} parole, circa {e['durata'] / 60:.1f} minuti stimati.\n"
                     f"Paper: {paper['link']}")
        avanz.fine(riepilogo)
        return 0
    except KeyboardInterrupt:
        avanz.scrivi("Interrotto a mano. Rilanciando, riprende da qui.")
        return 130
    except Exception as exc:
        avanz.errore(passo, exc)
        return 1
    finally:
        vram.ferma()


if __name__ == "__main__":
    sys.exit(main())

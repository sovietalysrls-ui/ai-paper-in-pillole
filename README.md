# AI Paper in Pillole — la catena notturna

Ogni notte il programma prende il paper più votato dei Daily Papers di
Hugging Face, lo legge, e prepara la puntata del podcast e l'articolo
per il sito. Tutto con modelli che girano sul tuo PC.

Questa è la **versione 1**: fa i passi 1-6, cioè tutta la parte di testo.
Voce, copertina, montaggio e WordPress arrivano nei prossimi passi.

## Cosa trovi la mattina

Nella cartella `~/AI-Paper-in-Pillole/OGGI`:

| File | Cos'è |
|---|---|
| `titolo.txt` | Il titolo della puntata, da copiare su Spotify e Amazon |
| `descrizione.txt` | La descrizione, con autori, link arXiv e hashtag |
| `dialogo.txt` | Il dialogo di Carlo e Arianna, da leggere |
| `articolo.html` | L'articolo per il sito (in futuro va su WordPress da solo) |
| `registro.log` | Il diario della notte: ogni passo con l'ora |
| `.lavoro/` | Cartella nascosta con i passaggi intermedi |

Il giorno dopo, tutto questo si sposta in `OLD/AAAA-MM-GG_#NN_nome/`.
I file wav vengono tolti dall'archivio perché sono grandi.

Dentro `.lavoro/it/` ci sono i file utili per capire cosa ha fatto il modello:

- `scheda.json`: la scheda dei fatti da cui nasce tutto. Se il dialogo
  dice una cosa sbagliata, di solito l'errore nasce qui.
- `dialogo_bozza.txt`: il dialogo prima dei controlli.
- `dialogo_finale.txt`: il dialogo dopo i controlli.
- `dialogo_voce.txt`: la versione che leggerà la voce, con i nomi
  inglesi scritti come si pronunciano.

## Installazione (una volta sola)

Su Linux, nel terminale. Ogni riga è un comando.

1. Copia la cartella `ai-paper-in-pillole` nella tua home.

2. Crea l'ambiente Python (una cartella che contiene le librerie solo
   per questo progetto, senza toccare il resto del sistema):

   ```
   cd ~/ai-paper-in-pillole
   python3 -m venv ~/venv-pillole
   ~/venv-pillole/bin/pip install -r requirements.txt
   ```

3. Installa Ollama (il programma che fa girare i modelli di testo),
   se non c'è già:

   ```
   curl -fsSL https://ollama.com/install.sh | sh
   ```

4. Scarica il modello di testo (circa 6 GB):

   ```
   ollama pull qwen3.5:9b
   ```

5. Prepara il file dei segreti:

   ```
   cp segreti.env.esempio segreti.env
   ```

   Poi aprilo e riempilo (vedi sotto la parte Telegram).

## Come si lancia

```
cd ~/ai-paper-in-pillole
~/venv-pillole/bin/python pipeline.py --prova
```

`--prova` lavora in `~/AI-Paper-in-Pillole-PROVA`, con un registro
separato. Le prove non consumano paper e non spostano la numerazione vera.
Togli `--prova` quando la catena va in produzione.

Altre opzioni utili:

| Opzione | Cosa fa |
|---|---|
| `--finto` | Niente modello: collauda solo il flusso in pochi secondi |
| `--paper 2610.01762` | Usa quel paper invece del più votato |
| `--rifai` | Butta il lavoro di oggi e ricomincia da capo |
| `--modello gemma4:e4b` | Prova un altro modello, solo per questa volta |
| `--data 2026-10-06` | Finge che oggi sia un altro giorno |

Se la catena si ferma (rete, modello, corrente), basta rilanciarla:
riparte dal passo interrotto.

## Cosa vedi a schermo

Una riga per ogni passo, con l'ora. Mentre il modello scrive, una riga
che si aggiorna con le parole scritte e i secondi passati. Alla fine,
il picco di memoria video usata: se supera il limite della GTX 1070
(7,5 GB, impostabile in `config.yaml`) compare un avviso.

## Telegram

1. Su Telegram cerca **@BotFather**, scrivi `/newbot` e segui le domande.
   Alla fine ti dà un codice lungo: è il `TELEGRAM_TOKEN`.
2. Apri la chat con il tuo bot nuovo e scrivigli qualunque cosa.
3. Nel browser apri
   `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates`
   e cerca `"chat":{"id":` seguito da un numero: è il `TELEGRAM_CHAT_ID`.
4. Metti i due valori in `segreti.env`.

Durante la notte ricevi un messaggio che si aggiorna a ogni passo.
Alla fine arriva un messaggio nuovo con l'esito (con notifica).
In caso di errore arriva subito un messaggio con il passo e il motivo.
Con `--finto` Telegram resta spento.

## Cosa si può cambiare senza toccare il codice

Tutto sta in file di testo:

- `config.yaml`: lingue, modello, durata massima, lunghezza articolo,
  stato WordPress (bozza o pubblica), limite di memoria video.
- `lingue/it/lingua.yaml`: carattere di Carlo e Arianna, presentazione,
  chiusura, testi fissi di descrizione e articolo.
- `lingue/it/vietate.yaml`: i tic da podcast artificiale. Per aggiungerne
  uno, copia un blocco e cambia le tre righe.
- `lingue/it/pronuncia.yaml`: come la voce deve leggere i nomi inglesi.
  Ogni notte il programma salva le pronunce nuove proposte dal modello in
  `dati/pronunce_proposte_it.yaml`: quelle giuste vanno copiate qui.
- `lingue/it/prompt/`: le istruzioni date al modello, una per compito.

## La versione inglese

È già pronta. In `config.yaml` metti:

```
lingue: [it, en]
```

La cartella OGGI avrà due sottocartelle, `it` e `en`. Il paper è lo
stesso per entrambe. La numerazione inglese parte da 1 (impostabile in
`numero_iniziale`). Nome del podcast e conduttori inglesi si cambiano in
`lingue/en/lingua.yaml`.

## Come lavora, in breve

1. **Scelta.** Legge le liste di Hugging Face partendo da ieri e
   andando indietro. Prende il paper più votato non ancora usato.
   Nel weekend, senza lista nuova, scende al secondo, al terzo, e così via.
2. **Lettura.** Prende da arXiv la versione web del paper e tiene
   introduzione, metodo, esperimenti, conclusioni e didascalie.
   Salta lavori correlati, appendici e bibliografia. Se la versione web
   manca, usa il PDF.
3. **Scheda dei fatti.** Il modello legge il paper a pezzi ed estrae i
   fatti. Poi li unisce in una scheda: problema, idea, risultati, limiti,
   esempio concreto, nomi e sigle con la pronuncia.
4. **Dialogo.** Scritto solo dalla scheda, con la struttura fissa:
   gancio, presentazione, paper, chiusura.
5. **Controlli.** Un programma (non il modello) cerca: espressioni
   vietate, frasi troppo lunghe, battute che fanno l'eco, numeri che non
   sono nella scheda, sigle spiegate due volte o in due lingue,
   struttura, lunghezza. Fa riscrivere solo le battute sbagliate.
   Al massimo tre giri. Ciò che resta va negli avvisi.
6. **Testi.** Titolo, descrizione e articolo, più un passaggio di
   correzione dei refusi.

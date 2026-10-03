# AI Paper in Pillole — la catena notturna

Ogni notte il programma prende il paper più votato dei Daily Papers di
Hugging Face, lo legge, e prepara la puntata del podcast e l'articolo
per il sito.

Funziona in due modi, con lo stesso codice:

- **Cloud (subito operativo):** gira di notte sui computer di GitHub,
  con Gemini per testo e voce. Niente PC acceso.
- **Locale (obiettivo finale):** gira sul PC con la GTX 1070, con
  modelli open source. Per ora il locale fa la parte di testo; la voce
  locale arriva dopo.

## Cosa ricevi la mattina (versione cloud)

Su Telegram, nella chat con il tuo bot:

1. un messaggio che durante la notte si aggiorna a ogni passo;
2. il **titolo** (tieni premuto per copiarlo);
3. la **descrizione** (idem);
4. la **copertina** (jpg);
5. la **puntata in mp3**, ascoltabile nel telefono;
6. la **puntata in wav**, da caricare su Spotify for Creators;
7. un messaggio finale con l'esito e gli eventuali avvisi.

Sul sito trovi l'articolo **in bozza**, con la copertina come immagine in
evidenza. Quando ti fidi, in `config.yaml` metti `stato: pubblica`.

Su Amazon non devi caricare nulla, se il podcast è collegato al feed RSS
di Spotify for Creators (vedi in fondo).

Nel repository, cartella `archivio/puntate/`, restano titolo,
descrizione, dialogo, articolo, copertina e scheda di ogni puntata.
L'audio no: è troppo pesante per GitHub. L'mp3 resta comunque nella
chat Telegram, e GitHub tiene una copia di tutti i file per 14 giorni
(scheda Actions, dentro l'esecuzione della notte).

## Mettere in funzione la versione cloud

Una volta sola, tutto dal browser.

### 1. Chiave Gemini gratuita

1. Vai su https://aistudio.google.com/apikey e accedi con un account Google.
2. "Create API key". Copia la chiave.
3. Se vuoi anche la riserva a pagamento, crea una seconda chiave in un
   progetto Google con la fatturazione attiva.

La chiave gratuita si usa per prima. Se esaurisce le richieste del
giorno, il programma passa da solo a quella a pagamento e te lo scrive
negli avvisi di Telegram.

### 2. Bot Telegram

1. Su Telegram cerca **@BotFather**, scrivi `/newbot` e segui le domande.
   Alla fine ti dà un codice lungo: è il `TELEGRAM_TOKEN`.
2. Apri la chat con il tuo bot nuovo e scrivigli qualunque cosa.
3. Nel browser apri
   `https://api.telegram.org/bot<IL_TUO_TOKEN>/getUpdates`
   e cerca `"chat":{"id":` seguito da un numero: è il `TELEGRAM_CHAT_ID`.

### 3. WordPress

1. Entra nella bacheca di andreamanini.it.
2. Utenti > Profilo > in fondo, "Password per le applicazioni".
3. Nome: `AI Paper in Pillole`. Premi "Aggiungi". Copia la password che compare
   (con gli spazi, va bene così).

È una password solo per questo programma. Non è quella con cui entri
nel sito e la puoi revocare quando vuoi.

### 4. I segreti su GitHub

Nel repository: **Settings > Secrets and variables > Actions > New repository secret**.
Crea questi, uno alla volta (nome a sinistra, valore copiato sopra):

| Nome | Valore |
|---|---|
| `GEMINI_API_KEY_GRATIS` | la chiave gratuita |
| `GEMINI_API_KEY_PAGAMENTO` | la chiave a pagamento (facoltativa) |
| `TELEGRAM_TOKEN` | il codice del bot |
| `TELEGRAM_CHAT_ID` | il numero della chat |
| `WP_UTENTE` | il tuo nome utente WordPress |
| `WP_PASSWORD_APP` | la password per applicazioni |

I segreti restano cifrati su GitHub. Nessuno li vede, nemmeno nei diari
delle notti.

### 5. Prima prova

Scheda **Actions** > **Notte** > **Run workflow**. Spunta **prova** e premi
il tasto verde. In 5-10 minuti arriva tutto su Telegram.

`prova` usa un registro separato: non consuma il paper e non sposta la
numerazione vera. Se la prova va bene, da quella notte la catena parte da sola.

## Orario

La notte parte alle 02:15 UTC: le 04:15 in Italia con l'ora legale, le
03:15 con l'ora solare. GitHub a volte parte con qualche minuto di ritardo.
L'orario si cambia nel file `.github/workflows/notte.yml`, riga `cron`.

## La sigla

`assets/sigla_apertura.wav` e `assets/sigla_chiusura.wav` sono generate
da `sigla.py`, nota per nota: sono musica tua, senza diritti di terzi.

Per sceglierne un'altra:

```
python sigla.py --varianti 6     # crea 6 varianti in assets/varianti/
python sigla.py --seme 3         # tiene la variante numero 3
```

Schema della puntata: gancio → sigla che sfuma sotto la presentazione →
paper → chiusura → sigla finale.

## La versione locale (PC con la GTX 1070)

```
cd ~
git clone https://github.com/sovietalysrls-ui/ai-paper-in-pillole
cd ai-paper-in-pillole
python3 -m venv ~/venv-pillole
~/venv-pillole/bin/pip install -r requirements.txt
sudo apt install ffmpeg
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3.5:9b
cp segreti.env.esempio segreti.env      # e riempilo
~/venv-pillole/bin/python pipeline.py --prova
```

I file finiscono in `~/AI-Paper-in-Pillole-PROVA/OGGI`. A fine lavoro il
programma scrive il picco di memoria video usata: se supera il limite
della GTX 1070 (7,5 GB) compare un avviso.

## Opzioni

| Opzione | Cosa fa |
|---|---|
| `--cloud` | Usa Gemini per testo e voce (profilo cloud di `config.yaml`) |
| `--prova` | Cartelle e registro separati: le prove non toccano la numerazione |
| `--finto` | Niente modelli: collauda il flusso in pochi secondi |
| `--paper 2610.01762` | Usa quel paper invece del più votato |
| `--rifai` | Butta il lavoro di oggi e ricomincia da capo |
| `--modello gemma4:e4b` | Prova un altro modello locale, solo per questa volta |
| `--voce nessuna` | Salta voce e montaggio |
| `--data 2026-10-06` | Finge che oggi sia un altro giorno |

Se la catena si ferma (rete, quota, modello), basta rilanciarla:
riparte dal passo interrotto.

## Cosa si può cambiare senza toccare il codice

- `config.yaml`: lingue, modelli, voci di Carlo e Arianna, durata
  massima, colori della copertina, stato WordPress (bozza o pubblica).
- `lingue/it/lingua.yaml`: carattere dei conduttori, presentazione,
  chiusura, testi fissi in fondo a descrizione e articolo.
- `lingue/it/vietate.yaml`: i tic da podcast artificiale. Per aggiungerne
  uno, copia un blocco e cambia le tre righe.
- `lingue/it/pronuncia.yaml`: come la voce locale deve leggere i nomi inglesi.
- `lingue/it/prompt/`: le istruzioni date al modello, una per compito.

## La versione inglese

È già pronta. In `config.yaml` metti `lingue: [it, en]`. Ogni lingua ha la
sua sottocartella, la sua numerazione e i suoi file. L'articolo sul sito
resta solo in italiano (`wordpress: lingue: [it]`).

## Amazon Music

Spotify for Creators pubblica un **feed RSS**: un indirizzo che elenca
tutte le puntate e si aggiorna da solo. Amazon lo legge e prende le
puntate nuove senza che tu faccia nulla.

Una volta sola: copia il feed RSS dalle impostazioni del podcast su
Spotify for Creators, vai su https://podcasters.amazon.com, incollalo e
conferma la proprietà via email.

## Come lavora, in breve

1. **Scelta.** Legge le liste di Hugging Face da ieri all'indietro e
   prende il paper più votato non ancora usato. Nel weekend, senza lista
   nuova, scende al secondo, al terzo, e così via.
2. **Lettura.** Prende da arXiv la versione web del paper: introduzione,
   metodo, esperimenti, conclusioni, didascalie. Salta lavori correlati,
   appendici e bibliografia. Se la versione web manca, usa il PDF.
3. **Scheda dei fatti.** Il modello estrae i fatti e li riunisce in una
   scheda: problema, idea, risultati, limiti, esempio concreto, nomi e sigle.
4. **Dialogo.** Scritto solo dalla scheda, con struttura fissa.
5. **Controlli.** Un programma (non il modello) cerca espressioni vietate,
   frasi lunghe, eco, ripetizioni, numeri inventati, sigle spiegate due
   volte, struttura e lunghezza. Fa riscrivere solo ciò che non va.
6. **Testi.** Titolo, descrizione e articolo, più una correzione dei refusi.
7. **Voce.** Il dialogo letto a due voci, a blocchi.
8. **Copertina.** Un disegno astratto nei colori fissi, con un motivo
   scelto dal tema del paper (onde, occhio, righe, griglia, strati, nodi...).
9. **Montaggio.** Sigle, pause, volume livellato a -16 LUFS (lo standard
   dei podcast). Esce wav e mp3.
10. **Sito.** Articolo su WordPress con copertina, categoria e tag.
11. **Consegna.** Tutto su Telegram.

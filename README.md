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
descrizione, dialogo, articolo, copertina, scheda e **mp3** di ogni puntata.

Il **wav** è troppo pesante per stare nelle cartelle del repository.
Va nelle **Releases**: nella pagina del repository, colonna di destra.
Ogni puntata ha la sua release, con wav, mp3 e copertina da scaricare.

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

## Google Drive

Ogni notte la puntata finisce anche su Drive, nella cartella
**AI Paper in Pillole**:

- `OGGI/`: la puntata appena fatta, completa (wav, mp3, titolo,
  descrizione, dialogo, articolo, copertina);
- `OLD/AAAA-MM-GG_NNN_nome/`: le puntate passate, senza il wav.

Serve un'autorizzazione, una volta sola, con rclone:

1. Scarica rclone per Windows da https://rclone.org/downloads/ e scompatta lo zip.
2. Nella cartella scompattata apri PowerShell e scrivi `.\rclone.exe config`.
3. Rispondi così: `n` (nuovo), nome `gdrive`, tipo `drive`, client id e
   secret vuoti (Invio), scope `1`, poi Invio a tutto il resto finché
   chiede "Use web browser to automatically authenticate?": rispondi `y`.
   Si apre il browser: accedi a Google e autorizza. "Shared Drive": `n`.
   Conferma con `y` e esci con `q`.
4. Scrivi `.\rclone.exe config show gdrive` e copia tutto il testo che compare,
   compresa la prima riga `[gdrive]`.
5. Su GitHub crea il segreto **RCLONE_CONF** e incolla quel testo.

## Orario

La notte parte alle 02:15 UTC: le 04:15 in Italia con l'ora legale, le
03:15 con l'ora solare. GitHub a volte salta una partenza: per questo ci sono
due sveglie di riserva, un'ora e due ore dopo. Se la puntata è già fatta,
escono subito senza fare nulla.
L'orario si cambia nel file `.github/workflows/notte.yml`, riga `cron`.

## La sigla

La sigla si crea una volta sola con **Lyria**, il modello musicale di
Google, usando la stessa chiave Gemini.

1. Actions > **Sigla** > Run workflow, azione **proponi**. In pochi minuti
   arrivano su Telegram 6 proposte in stili diversi (tech, indie pop,
   funky, lo-fi allegro, acustico, synthwave). Nel campo "stile" puoi
   scrivere uno stile tuo, per esempio "funky con basso slap e fiati".
2. Ascolta, scegli il numero.
3. Actions > **Sigla** > Run workflow, azione **usa**, numero scelto.
   Il programma prende i primi 7 secondi per l'apertura e gli ultimi 8
   per la chiusura, con le sfumature.

Finché la sigla non c'è, le puntate escono senza musica.

Schema della puntata: gancio → presentazione → sigla → paper → chiusura →
sigla finale.

L'audio di Lyria contiene SynthID, una filigrana digitale non udibile
che indica che il brano è generato da un'AI.

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
| `--solo-testi` | Solo dialogo e articolo: niente voce, copertina disegnata (per rivederli) |
| `--paper ID --sostituisci` | Rifà una puntata già uscita: stesso numero, articolo aggiornato, audio sostituito |
| `--se-manca` | Esce subito se la puntata di oggi è già fatta (lo usano le sveglie di riserva) |

Da GitHub: Actions > Notte > Run workflow ha le stesse caselle
(paper, prova, solo testi, sostituisci, solo articolo). Se una notte si
interrompe, copia il numero dell'esecuzione dal suo indirizzo e inseriscilo in
**riprendi da**: vengono ricaricati i file salvati e si riparte soltanto dal
passo non concluso. Il workflow prova già una seconda volta automaticamente
sullo stesso checkpoint prima di fermarsi.

## Le regole dei testi, in breve

- Al massimo 4 numeri nel dialogo, sempre spiegati con un paragone. I numeri precisi stanno nell'articolo.
- Niente nomi inglesi dei test e niente versioni dei modelli nel dialogo.
- Punteggi senza un massimo (Elo, classifiche): mai un fondo scala inventato.
- Mai "divulgazione scientifica".
- Articolo e descrizione passano un controllo automatico e una revisione.

## La frase finale

"AI Paper in Pillole è un progetto di Sovietaly SRLS" è una registrazione fissa:
`assets/firma_it.wav`. Per cambiarla: Actions > Firma > proponi, ascolta su
Telegram, poi Actions > Firma > usa con il numero scelto.

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

Sei un lettore attento di paper scientifici di intelligenza artificiale.
Il tuo lavoro è estrarre fatti, senza commentarli e senza inventare nulla.
Scrivi in italiano. Rispondi solo con JSON.
---UTENTE---
Paper: «$titolo»
Parte: $sezione

Leggi il testo tra <<< e >>> ed estrai solo ciò che c'è scritto.

Regole:
- "fatti": da 3 a 8 frasi brevi in italiano, una informazione per frase. Cosa fanno, come, perché.
- "numeri": i risultati numerici importanti, con il valore esatto come scritto nel testo (per esempio "96.0%" o "3x") e cosa misura in parole semplici. Massimo 6. Se non ci sono numeri, lista vuota.
- "esempi": situazioni concrete o casi d'uso descritti nel testo. Se non ci sono, lista vuota.
- "limiti": limiti o problemi che gli autori ammettono. Se non ci sono, lista vuota.
- "termini": nomi propri (modelli, aziende, università, dataset) e sigle che compaiono e contano per capire il paper. Massimo 8.
- Non riportare formule. Non riportare riferimenti ad altri paper.

<<<
$testo
>>>

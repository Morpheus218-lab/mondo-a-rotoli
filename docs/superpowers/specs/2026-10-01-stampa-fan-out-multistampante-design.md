# Stampa fan-out: ogni stampante stampa tutti i messaggi — design

Data: 2026-10-01

## Contesto

Oggi più Raspberry Pi con stampante, in luoghi diversi, interrogano lo
stesso `hosting/api/claim.php`: quell'endpoint fa una `SELECT ... FOR
UPDATE` e marca il messaggio come `printing`, in modo che **un solo**
poller se lo accaparri — disegno corretto quando c'era una sola
stampante, sbagliato ora: un messaggio finisce stampato da una sola
delle stampanti, mai dalle altre.

## Obiettivo

- Ogni Raspberry Pi stampante stampa in autonomia **tutti** i messaggi
  nuovi, senza competere con le altre per lo stesso messaggio.
- Al primo avvio (Pi nuovo, o Pi esistente che riceve questo nuovo
  codice) **non si stampa nulla** di già esistente: solo i messaggi che
  arrivano dopo quel primo avvio.
- Riusa il pattern già scritto, testato e in produzione in
  `bridge/fetcher.py` — stesso schema MySQL, nessuna tabella nuova,
  basso rischio.

## Architettura

```
hosting/api/message.php                    Ogni Pi stampante (N, indipendenti)
  inserisce con status='delivered'          poller.py (ogni 5s)
  direttamente (niente piu' pending)          |
        |                                      v
        v                                  GET /api/history.php (pubblico)
hosting/api/history.php                       |
  invariato (piu' recenti prima)                v
  (restituisce tutti i delivered)          confronta con il proprio file
                                            locale (insieme di id gia'
                                            stampati) -> stampa solo i
                                            messaggi mai visti -> li
                                            registra nel file locale
                                            SOLO dopo stampa riuscita
```

`hosting/api/claim.php` e `hosting/api/ack.php` vengono rimossi: nessuno
"prende in carico" un messaggio in esclusiva, quindi la transazione
`FOR UPDATE`/stato `printing` non serve più.

## Componenti

- **`hosting/api/message.php`** — l'insert usa `status='delivered'`
  invece di `'pending'`. Validazione e rate limit per IP invariati.
- **`hosting/api/claim.php`**, **`hosting/api/ack.php`** — rimossi dal
  repo (non più referenziati da nessun client).
- **`hosting/api/history.php`** — invariato: seleziona `status =
  'delivered'`, che ora è lo stato di ogni messaggio fin dall'invio.
- **`hosting/schema.sql`** — invariato. La colonna `status` resta
  `ENUM('pending','printing','delivered')`: semplificarla ora
  richiederebbe una migrazione in produzione, fuori scope per un fix
  veloce. Dopo questo cambio, semplicemente, `message.php` non scrive
  più `pending`.
- **`backend/api_client.py`** — sostituito da una funzione di recupero
  storico via `GET /history.php` (stesso ruolo di
  `bridge/api_client.py:recupera_storico`), al posto di
  `reclama_messaggio`/`conferma_messaggio`.
- **`backend/poller.py`** — riscritto sul modello di
  `bridge/fetcher.py`: dedup per insieme di id persistito in un file
  locale (stesso principio di `bridge/fetcher.py`, incluso tollerare
  righe corrotte ignorandole con un warning). Differenza esplicita dal
  bridge, vedi sotto: **al primo avvio non stampa nulla**.
- **`backend/printer.py`** — invariato.
- **`.env`** di ogni Pi stampante — nuova variabile opzionale
  `PRINTER_ID` (es. `PRINTER_ID=napoli`), usata solo nei log per
  distinguere i Pi quando si guardano più log insieme. Non influenza
  nessuna logica.

## Comportamento al primo avvio (il punto che differisce dal bridge)

- **Se il file locale non esiste** (primo avvio in assoluto per quel
  Pi, oppure primo avvio di un Pi esistente dopo aver ricevuto questo
  nuovo codice): il poller recupera lo storico attuale e scrive **tutti**
  quegli id nel file locale come "già visti", **senza stampare nulla**,
  poi esce dal ciclo. Da quel momento quel Pi considera "nuovo" solo
  ciò che arriva dopo.
- **Ai cicli successivi**: dedup per insieme di id come nel bridge —
  stampa solo i messaggi con id non ancora nel file locale, dal più
  vecchio al più nuovo.
- **Un messaggio viene registrato come "visto" solo dopo stampa
  riuscita.** Se la stampa fallisce, quel messaggio resta fuori dal
  file locale: verrà ritentato automaticamente al ciclo successivo.
  Questo sostituisce il vecchio meccanismo "stato `printing` bloccato,
  da sbloccare a mano" — qui il recupero è automatico, locale, senza
  bisogno di intervento manuale.
- **Se un messaggio fallisce, i successivi dello stesso ciclo non
  vengono stampati**: ci si ferma al primo fallimento invece di saltare
  avanti, per non stampare fuori ordine o lasciare un buco. Tutti i
  messaggi non ancora stampati (quello fallito e quelli dopo) restano
  "nuovi" e verranno ritentati insieme al ciclo successivo.

## Rollout (ordine importante)

1. Deploy del nuovo codice: `hosting/api/` (message.php aggiornato,
   claim.php/ack.php rimossi) e il nuovo `backend/poller.py` su **ogni**
   Pi stampante.
2. Avvia ogni Pi stampante col nuovo codice: ciascuno fa il proprio
   primo avvio "silenzioso" (baseline, nessuna stampa).
3. **Solo dopo** che tutti i Pi hanno completato il primo avvio, se
   restano messaggi bloccati in `pending`/`printing` da prima del
   deploy, sbloccali una volta sola:
   ```sql
   UPDATE messaggi SET status = 'delivered' WHERE status IN ('pending', 'printing');
   ```
   Farlo **prima** del punto 2 li farebbe assorbire silenziosamente
   nella baseline di qualche Pi, che non li stamperebbe mai (restano
   comunque visibili online, essendo `delivered`).
4. Verifica: invia un messaggio di test dal sito, conferma che
   **tutte** le stampanti lo stampino entro una decina di secondi.

## Gestione errori

- `text` mancante/vuoto/troppo lungo, rate limit: invariato
  (`message.php`).
- Storico irraggiungibile da un Pi (rete, hosting giù): loggato,
  riprovato al ciclo successivo — nessun impatto sugli altri Pi.
- Stampa fallita su un Pi: vedi sopra (nessuna registrazione, retry
  automatico, batch fermato al primo fallimento).
- File locale con una riga corrotta (es. scrittura interrotta da uno
  spegnimento): riga ignorata con un warning, le altre righe restano
  valide — stesso comportamento già in `bridge/fetcher.py`.
- `history.php` restituisce al massimo 100 messaggi per chiamata (stesso
  limite già noto per il bridge, vedi `bridge/README.md`): se un Pi
  resta spento o irraggiungibile abbastanza a lungo da accumulare più
  di 100 messaggi nuovi nel frattempo, quelli più vecchi della finestra
  dei 100 più recenti non vengono recuperati retroattivamente da quel
  Pi — restano comunque stampati dagli altri Pi che non hanno perso il
  giro, e visibili online.

## Testing

- `backend/tests/` riscritti sul modello di `bridge/tests/`: mock della
  funzione di recupero storico, copertura di: primo avvio non stampa
  nulla, dedup dei messaggi già stampati, un fallimento di stampa non
  registra il messaggio e ferma il batch (i successivi non vengono
  stampati in quel ciclo), riga locale corrotta ignorata senza bloccare
  la lettura.
- `backend/printer.py` — test esistenti invariati.
- Manuale: almeno due Pi (o due cartelle locali che simulano due Pi
  con stampanti diverse) che ricevono lo stesso messaggio e lo
  stampano entrambi, senza intervento manuale.

## Fuori scope

- Visibilità server-side di quali stampanti hanno già stampato un dato
  messaggio (richiesto esplicitamente: solo log locali per ora).
- Semplificazione dell'ENUM `status` nello schema MySQL.
- Interfaccia per aggiungere/rimuovere stampanti dinamicamente: restano
  configurate manualmente via `.env`, come già oggi per il Pi singolo.

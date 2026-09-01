# Backend su Raspberry Pi — design

Data: 2026-09-01

## Contesto

Il sistema attuale è diviso in tre parti:

1. **Frontend** (`frontend/index.html`) — pagina statica, invariata in questo design.
   Chiama `POST /message` per inviare un testo e `GET /message/history` per
   mostrare lo storico.
2. **Worker Cloudflare** (repo `txtinstallazione`, TypeScript/Hono + D1) — API
   che salva i messaggi in coda (`pending` → `delivered`) ed espone
   `/message`, `/message/latest`, `/message/ack`, `/message/history`.
3. **`poller.py`** (girava già sul Raspberry Pi Zero) — ogni 2 secondi
   interroga `/message/latest` sul Worker, se trova un messaggio pending lo
   renderizza come immagine (font Press Start 2P, 165px, ruotata 90°) e lo
   stampa su una stampante termica USB via `python-escpos`
   (`Usb(0x0416, 0x5011, ...)`), poi conferma con `/message/ack`.

## Obiettivo

Eliminare il Worker Cloudflare e D1. Il Raspberry Pi diventa l'unico
backend: riceve le richieste del frontend direttamente e stampa senza
passare da un servizio esterno. L'esposizione del Pi su internet (dominio,
port forwarding, tunnel, ecc.) è **fuori scope da questo design** — verrà
decisa separatamente; qui si assume che il Pi sia raggiungibile all'indirizzo
che verrà configurato in `frontend/index.html` (`API_URL`).

## Architettura

Un unico processo Python (Flask) sostituisce Worker + D1 + poller:

```
Frontend (POST /message) --> Flask app --> SQLite locale (pending)
                                  |
                                  v
                          Queue.Queue (in memoria)
                                  |
                                  v
                    Thread worker (stampa seriale)
                                  |
                                  v
                    Stampante USB (python-escpos)
                                  |
                                  v
                    SQLite locale: pending -> delivered

Frontend (GET /message/history) <-- Flask app <-- SQLite locale (delivered)
```

Un solo thread worker consuma la coda e stampa un messaggio alla volta:
la stampante USB è una risorsa non thread-safe, quindi va serializzato
l'accesso — è la stessa garanzia FIFO che il vecchio schema pending/delivered
offriva via polling, portata dentro lo stesso processo.

## Componenti

- **`backend/app.py`** — server Flask, definisce le rotte HTTP e inizializza
  DB, coda e thread worker all'avvio.
- **`backend/db.py`** — apertura connessione SQLite, funzioni di inserimento
  e lettura messaggi.
- **`backend/printer.py`** — logica di stampa, portata quasi identica da
  `poller.py` esistente (creazione immagine col font, invio a `Usb`).
- **`backend/fonts/PressStart2P.ttf`** — già presente, invariato.
- **`backend/schema.sql`** — stesso schema della tabella `messaggi` già
  usata su D1.

## Modello dati (SQLite locale)

Stessa tabella già in uso su D1, nessuna modifica:

```sql
CREATE TABLE IF NOT EXISTS messaggi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
);
```

## Endpoint

- **`POST /message`** — body `{ "text": "..." }`.
  - Valida: testo non vuoto, ≤100 caratteri (stesso limite già presente in
    `poller.py` e nel frontend).
  - Inserisce riga con `status='pending'`.
  - Mette l'id in coda per la stampa.
  - Risponde subito `202 { ok: true, id, createdAt }` — non aspetta che la
    stampa finisca.
- **`GET /message/history?limit=&offset=`** — legge righe con
  `status='delivered'`, ordine decrescente, stessa paginazione già usata dal
  frontend (`limit`, `offset`).
- CORS abilitato su tutte le rotte (il frontend gira da un'origine diversa).

Non sono più esposti `/message/latest` e `/message/ack`: erano necessari
solo per il polling esterno, ora la stampa è interna allo stesso processo.

## Flusso di stampa

1. Il thread worker estrae un id dalla coda.
2. Legge il testo dal DB.
3. Se >100 caratteri: stampa un messaggio di avviso invece del testo
   (comportamento invariato da `poller.py`).
4. Altrimenti: genera l'immagine col font Press Start 2P e la invia alla
   stampante.
5. In caso di successo, aggiorna la riga a `status='delivered'`.
6. In caso di eccezione durante la stampa: la riga resta `pending`, l'errore
   viene loggato, e l'id **non** viene rimesso automaticamente in coda in
   questa iterazione (per evitare loop infiniti su un errore persistente,
   es. stampante scollegata) — verrà ripreso al prossimo avvio del processo
   (vedi sotto).

## Avvio e crash recovery

All'avvio del processo, prima di aprire il server HTTP:

1. Apre/crea il DB SQLite se non esiste.
2. Legge tutte le righe `status='pending'` (messaggi mai stampati, es. per un
   crash o riavvio del Pi) e le rimette in coda in ordine di id crescente.
3. Avvia il thread worker.
4. Avvia il server Flask.

## Gestione errori

- Richiesta senza `text` o vuota → `400`.
- Testo >100 caratteri → accettato ma stampato come avviso (non è un errore
  utente, comportamento esistente).
- Stampante non raggiungibile/errore USB → loggato, messaggio resta
  `pending`, ripreso al riavvio del processo.
- DB non scrivibile → `500`, nessuna stampa (non si può accodare senza id).

## Testing

- Test manuale end-to-end: invio da frontend (o `curl`) → verifica stampa
  fisica e comparsa in `/message/history`.
- Test della validazione (`400` su testo vuoto/mancante).
- Test del comportamento >100 caratteri (stampa l'avviso, non il testo).
- Test di crash recovery: inserire una riga `pending` manualmente nel DB,
  riavviare il processo, verificare che venga stampata.
- La logica di stampa (creazione immagine, chiamata a `Usb`) non è
  facilmente testabile in automatico senza hardware — verifica manuale sul
  Pi con la stampante collegata.

## Fuori scope

- Esposizione del Pi su internet (dominio, port forwarding, tunnel, VPN) —
  discussa a parte, non blocca questo design.
- Autenticazione/rate limiting sull'endpoint `POST /message`.
- Migrazione dati storici già presenti su D1 (se servono, si esportano a
  parte).

# Frontend su hosting + backend PHP/MySQL + polling dal Pi — design

Data: 2026-09-11

## Contesto

Il sistema attuale (vedi [2026-09-01-backend-raspberry-design.md](2026-09-01-backend-raspberry-design.md))
ha consolidato tutto su un unico processo Flask+SQLite sul Raspberry Pi: il
frontend chiama direttamente il Pi via HTTP. Questo però richiede che il Pi
sia raggiungibile da internet (dominio, port forwarding, tunnel...), problema
lasciato esplicitamente fuori scope in quel design.

Prima ancora, il sistema era: Frontend → Cloudflare Worker + D1 → `poller.py`
sul Pi (polling ogni 2s). Quell'architettura è stata eliminata per ridurre il
numero di servizi da mantenere.

Ora si vuole un'architettura che risolva il problema del Pi dietro NAT
domestico senza reintrodurre un servizio esterno nuovo: il dominio
`mondoarotoli.cuoredinapoli.net` (hosting condiviso con PHP + MySQL già
disponibili) ospiterà sia il frontend statico sia un piccolo backend PHP che
funge da coda; il Pi farà polling in uscita su quel backend ogni 5 secondi.

## Obiettivo

- Frontend statico servito da `mondoarotoli.cuoredinapoli.net`.
- Un backend PHP + MySQL, sullo stesso hosting/dominio, che riceve i
  messaggi dal frontend e li tiene in coda.
- Il Raspberry Pi non espone più nulla su internet: ogni 5 secondi
  interroga il backend PHP, stampa i messaggi pending e conferma la stampa.
- Nessuna stampa duplicata per lo stesso invio, anche in caso di problemi
  di rete durante la conferma.
- Protezione anti-abuso (rate limit) sull'endpoint pubblico di invio.

## Architettura

```
Frontend statico (mondoarotoli.cuoredinapoli.net)
        |  POST /api/message.php   (pubblico)
        |  GET  /api/history.php   (pubblico)
        v
PHP + MySQL (stesso hosting, stessa origine → niente CORS)
        ^
        |  POST /api/claim.php     (privato, richiede API key)
        |  POST /api/ack.php       (privato, richiede API key)
        v
Raspberry Pi: poller.py (loop ogni 5s) --> printer.py --> stampante USB
```

Il Pi non ha più un DB locale né un server HTTP: diventa un client che fa
solo richieste in uscita. Frontend e backend PHP sono sulla stessa origine,
quindi non serve gestire CORS lato PHP.

## Componenti

- **Backend PHP** (nuova cartella `hosting/` nel repo, da caricare
  sull'hosting):
  - `api/message.php` — riceve nuovi messaggi dal frontend.
  - `api/history.php` — storico messaggi consegnati, per il frontend.
  - `api/claim.php` — riservato al Pi: reclama il prossimo messaggio pending.
  - `api/ack.php` — riservato al Pi: conferma la stampa di un messaggio.
  - `config.php` — credenziali DB e API key condivisa col Pi (non
    committato: `config.php.example` come template).
  - `db.php` — apertura connessione PDO, riusata dagli endpoint.
- **`backend/poller.py`** (nuovo, sostituisce `app.py`) — loop principale sul
  Pi: ogni 5 secondi chiama `claim.php`, stampa con `printer.py`, poi chiama
  `ack.php`.
- **`backend/printer.py`** — invariato.
- **File rimossi dal Pi**: `backend/app.py`, `backend/db.py`,
  `backend/schema.sql` (lo schema si sposta nel backend PHP, vedi sotto),
  relativi test (`test_app.py`, `test_db.py`).
- **`backend/txtinstallazione.service`** — aggiornato per lanciare
  `poller.py` invece di `app.py`.
- **`frontend/index.html`** — cambia solo `API_URL` per puntare ai nuovi
  endpoint PHP (stesso dominio del frontend, quindi si può anche usare un
  path relativo `/api/...` invece di un URL assoluto).

## Modello dati (MySQL)

```sql
CREATE TABLE IF NOT EXISTS messaggi (
  id INT AUTO_INCREMENT PRIMARY KEY,
  text VARCHAR(1000) NOT NULL,
  created_at DATETIME NOT NULL,
  status ENUM('pending', 'printing', 'delivered') NOT NULL DEFAULT 'pending',
  ip VARCHAR(45) NOT NULL
) ENGINE=InnoDB;

CREATE INDEX idx_messaggi_status_id ON messaggi (status, id);
CREATE INDEX idx_messaggi_ip_created_at ON messaggi (ip, created_at);
```

Stessa forma logica dello schema SQLite attuale (id, text, created_at,
status), con l'aggiunta di:
- stato intermedio `printing` (vedi sezione claim/ack sotto);
- colonna `ip`, usata solo per il rate limit (non esposta nelle risposte
  pubbliche).

Compatibile con una futura importazione dello storico da
`installazione.db`: uno script una tantum potrà inserire le vecchie righe
con il loro `created_at` originale e `status='delivered'`. Non viene
costruito in questa fase.

## Endpoint pubblici

### `POST /api/message.php`
Body: `{"text": "..."}`.

Validazione (stessa di oggi in `app.py`):
- `text` deve essere una stringa non vuota dopo `trim`.
- lunghezza massima 1000 caratteri (limite di validazione lato API; il
  limite dei 100 caratteri "stampabili senza avviso" resta una decisione di
  `printer.py`, invariata).
- body JSON limitato in dimensione (stessa soglia di oggi, 64KB).

Rate limit per IP: se l'IP chiamante ha già inserito **5 o più messaggi
negli ultimi 2 minuti**, risponde `429` con un messaggio d'errore. Valori
configurabili in `config.php`.

Successo: inserisce riga con `status='pending'`, risponde `202
{"ok": true, "id": ..., "createdAt": ...}` — stesso contratto di oggi.

### `GET /api/history.php?limit=&offset=`
Stessa semantica di oggi: righe con `status='delivered'`, ordine
decrescente per id, `limit` e `offset` con gli stessi clamp attuali
(`limit` tra 1 e 100, `offset` ≥ 0). Non include mai la colonna `ip`.

## Endpoint privati (solo Pi)

Entrambi richiedono l'header `X-Api-Key` con un valore segreto condiviso,
generato una volta e messo sia in `config.php` (hosting) sia nella
configurazione del Pi (variabile d'ambiente o file locale non committato).
Richiesta senza chiave valida → `401`, nessuna azione. Questo evita che
chiunque conosca l'URL possa reclamare o scartare messaggi al posto del Pi.

### `POST /api/claim.php`
Nessun body. In una singola transazione:
1. Seleziona l'id del messaggio `pending` più vecchio (`ORDER BY id ASC
   LIMIT 1`, con `FOR UPDATE` per evitare corse se mai ci fosse più di un
   poller).
2. Se esiste, lo aggiorna a `status='printing'` e lo restituisce
   (`{"id": ..., "text": ...}`).
3. Se non esiste nulla, risponde `204 No Content`.

### `POST /api/ack.php`
Body: `{"id": ...}`. Aggiorna la riga a `status='delivered'` **solo se** lo
stato attuale è `printing` (evita di "consegnare" due volte o di
sovrascrivere una riga già tornata pending manualmente). Risponde `200
{"ok": true}` o `404` se l'id non è in stato `printing`.

## Garanzia "mai due stampe per lo stesso invio"

Una volta che un messaggio passa a `printing` (claim riuscito), **non
esiste alcun meccanismo automatico che lo riporti a `pending`**: niente
timeout, niente scadenza del claim. Il worker sul Pi stampa localmente via
USB (operazione che non dipende dalla rete) e solo dopo prova a confermare
con `ack.php`.

Questo significa:
- Se il claim ha successo e la stampa ha successo e l'ack ha successo →
  flusso normale, nessun problema.
- Se il claim ha successo ma la stampa fallisce (es. stampante
  scollegata) → il messaggio resta `printing` per sempre finché non viene
  sbloccato manualmente (vedi sotto). Non viene ristampato automaticamente,
  ma nemmeno perso silenziosamente: resta visibile in MySQL con stato
  `printing`, distinguibile da `pending` e `delivered`.
- Se claim e stampa hanno successo ma l'`ack` fallisce per un problema di
  rete → stesso comportamento: il messaggio resta `printing`, non viene
  ristampato al giro successivo (perché `claim.php` seleziona solo righe
  `pending`).

**Recupero manuale**: un messaggio bloccato in `printing` va sbloccato a
mano con una query diretta sul DB (es. tramite phpMyAdmin dell'hosting):
```sql
UPDATE messaggi SET status = 'pending' WHERE id = ...;
```
Questo va fatto consapevolmente solo se si è certi che il messaggio non sia
stato effettivamente stampato (altrimenti si otterrebbe una stampa
duplicata) — è una scelta esplicita: si preferisce un messaggio bloccato,
visibile e recuperabile a mano, piuttosto che un rischio automatico di
doppia stampa. Il comando va documentato in `backend/README.md`.

## Flusso di stampa (`poller.py`)

1. Ogni 5 secondi, chiama `POST /api/claim.php` con l'API key.
2. Se `204` (niente da stampare), attende e ricomincia.
3. Se arriva un messaggio, chiama `printer.stampa_messaggio` (logica
   invariata, incluso il comportamento per testi oltre i 100 caratteri).
4. Se la stampa ha successo, chiama `POST /api/ack.php` con l'id.
   - Se l'ack fallisce (rete), logga l'errore e prosegue al giro
     successivo: **non** ritenta subito l'ack né rimette in coda da solo
     (vedi sezione precedente).
5. Se la stampa fallisce (eccezione o esito negativo da
   `stampa_messaggio`), logga l'errore e **non** chiama `ack.php`: il
   messaggio resta `printing` e va sbloccato a mano come sopra.
6. Qualsiasi eccezione imprevista nel ciclo viene loggata; il loop continua
   (stesso pattern difensivo di `worker_loop` oggi).

Errori di rete su `claim.php` stesso (hosting irraggiungibile) vengono
loggati e il poller riprova al giro successivo, senza terminare il
processo (`txtinstallazione.service` ha comunque `Restart=always` come
rete di sicurezza).

## Gestione errori (endpoint PHP)

- `text` mancante/vuoto/non stringa → `400`.
- `text` oltre 1000 caratteri → `400`.
- body oltre 64KB → `413`.
- rate limit superato → `429`.
- richiesta privata senza API key valida → `401`.
- `ack` su id non in stato `printing` → `404`.
- errore di connessione al DB → `500`, loggato lato server (non esporre
  dettagli interni nella risposta).

## Sicurezza

- Tutte le query usano prepared statement (PDO) — nessuna concatenazione
  di input utente in SQL.
- `config.php` (credenziali DB + API key) non viene committato; si aggiunge
  `config.php.example` come riferimento e si aggiorna `.gitignore`.
- L'endpoint pubblico non espone mai la colonna `ip`.
- HTTPS per tutte le chiamate (hosting e chiamate del Pi verso l'hosting).

## Testing

- **`poller.py`**: test unitari che mockano le chiamate HTTP (stesso stile
  di `test_worker.py` esistente, che mocka `printer`), coprendo: nessun
  messaggio da stampare, stampa riuscita + ack riuscito, stampa fallita
  (nessun ack chiamato), ack fallito dopo stampa riuscita (nessun retry
  automatico), errore di rete su claim.
- **`printer.py`**: invariato, i test esistenti restano validi così come
  sono.
- **Endpoint PHP**: verifica manuale (`curl`) secondo una checklist in
  `backend/README.md` — invio messaggio, rispetto del rate limit, storico,
  claim/ack con e senza API key valida. Non si introduce un framework di
  test PHP in questa fase (nessuno già presente nel repo).
- **End-to-end manuale**: invio dal frontend reale (o `curl` contro
  l'hosting) → verifica stampa fisica sul Pi → comparsa in
  `/api/history.php`.

## Fuori scope

- Migrazione effettiva dei messaggi storici da `installazione.db` a MySQL
  (lo schema la rende possibile in futuro, ma lo script non viene scritto
  ora).
- Sblocco automatico di messaggi rimasti `printing` (deliberatamente
  manuale, vedi sopra).
- Framework di test automatico per gli endpoint PHP.
- Autenticazione/rate limit più sofisticati di un semplice conteggio per
  IP in finestra temporale (es. niente CAPTCHA, niente WAF).
- Deploy automatico del codice PHP sull'hosting (si assume caricamento
  manuale via FTP/pannello, come per un hosting condiviso tipico).

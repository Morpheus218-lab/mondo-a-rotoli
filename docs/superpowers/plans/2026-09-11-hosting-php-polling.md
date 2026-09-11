# Frontend su hosting + backend PHP/MySQL + polling dal Pi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Spostare il frontend su hosting web esterno con un backend PHP/MySQL come coda messaggi, e far diventare il Raspberry Pi un semplice client che fa polling ogni 5 secondi per stampare, senza mai esporsi su internet.

**Architecture:** Frontend statico e 4 endpoint PHP (message/history pubblici, claim/ack privati con API key) condividono lo stesso hosting e la stessa tabella MySQL `messaggi` (con stato intermedio `printing` per evitare doppie stampe). Il Raspberry Pi perde Flask e SQLite: un nuovo `poller.py` chiama `claim.php` ogni 5s, stampa con il `printer.py` esistente (invariato) e conferma con `ack.php`.

**Tech Stack:** PHP 7.4+/PDO/MySQL (hosting condiviso), Python 3 + `requests` (Pi), Pillow e `python-escpos` esistenti (invariati).

**Spec:** [docs/superpowers/specs/2026-09-11-hosting-php-polling-design.md](../specs/2026-09-11-hosting-php-polling-design.md)

## Global Constraints

- Tutte le query SQL lato PHP usano prepared statement PDO — mai concatenare input utente in SQL.
- `hosting/api/config.php` non va mai committato; solo `config.php.example` è tracciato in git.
- Gli endpoint privati (`claim.php`, `ack.php`) richiedono l'header `X-Api-Key`, confrontato con `hash_equals` (confronto a tempo costante).
- Limite testo: 1000 caratteri lato validazione API (invariato il limite di stampa di 100 caratteri di `printer.py`, che resta separato e invariato).
- Rate limit di default: 5 messaggi ogni 2 minuti per IP, configurabile in `config.php`.
- Un messaggio passato a `status='printing'` non torna mai automaticamente a `pending`: nessun timeout/scadenza automatica, solo sblocco manuale via SQL diretto.
- La tabella `messaggi` usa `ENGINE=InnoDB` (necessario per `SELECT ... FOR UPDATE` in `claim.php`).
- Tutte le chiamate del Pi verso l'hosting sono in HTTPS.

---

## Task 1: Schema MySQL + template di configurazione

**Files:**
- Create: `hosting/schema.sql`
- Create: `hosting/api/config.php.example`
- Modify: `.gitignore`

**Interfaces:**
- Produce: la tabella MySQL `messaggi (id, text, created_at, status, ip)` con `status` in `('pending', 'printing', 'delivered')`, usata da tutti gli endpoint PHP dei task successivi.
- Produce: il formato del file `config.php` (array associativo con chiavi `db_host`, `db_name`, `db_user`, `db_pass`, `api_key`, `rate_limit_max_messaggi`, `rate_limit_finestra_minuti`), che `hosting/api/db.php` (Task 2) leggerà con `require`.

- [ ] **Step 1: Scrivi lo schema MySQL**

```sql
-- hosting/schema.sql
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

- [ ] **Step 2: Scrivi il template di configurazione**

```php
<?php
// hosting/api/config.php.example
// Copiare questo file in config.php (stessa cartella) e compilare con i
// valori reali. config.php NON va committato — vedi .gitignore.

return [
    'db_host' => 'localhost',
    'db_name' => 'nome_database',
    'db_user' => 'utente_database',
    'db_pass' => 'password_database',
    // Genera una stringa lunga e casuale, es: php -r "echo bin2hex(random_bytes(32));"
    'api_key' => 'genera-una-chiave-lunga-e-casuale-qui',
    'rate_limit_max_messaggi' => 5,
    'rate_limit_finestra_minuti' => 2,
];
```

- [ ] **Step 3: Aggiungi `config.php` al `.gitignore`**

Apri `.gitignore` e aggiungi in fondo:

```
hosting/api/config.php
```

- [ ] **Step 4: Verifica manuale**

Su un'istanza MySQL (locale o sull'hosting, es. tramite phpMyAdmin o client CLI `mysql`), esegui `hosting/schema.sql` e poi:

```sql
DESCRIBE messaggi;
```

Verifica che compaiano le colonne `id, text, created_at, status, ip` e che `status` sia un `enum('pending','printing','delivered')`.

Copia `hosting/api/config.php.example` in `hosting/api/config.php` compilandolo con le credenziali del tuo database di test (questo file NON va committato, serve solo per i task successivi).

- [ ] **Step 5: Commit**

```bash
git add hosting/schema.sql hosting/api/config.php.example .gitignore
git commit -m "feat: aggiungi schema MySQL e template di configurazione per il backend PHP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Helper di connessione PHP (`db.php`) + endpoint `message.php`

**Files:**
- Create: `hosting/api/db.php`
- Create: `hosting/api/message.php`

**Interfaces:**
- Consuma: il file `config.php` prodotto dal Task 1 (chiavi `db_host`, `db_name`, `db_user`, `db_pass`, `api_key`, `rate_limit_max_messaggi`, `rate_limit_finestra_minuti`).
- Produce (`db.php`, riusato da tutti gli endpoint successivi):
  - `get_config(): array` — legge e ritorna `config.php`, termina con `500` se il file manca.
  - `get_db(): PDO` — connessione PDO con `ERRMODE_EXCEPTION` e `FETCH_ASSOC`, termina con `500` se la connessione fallisce.
  - `require_api_key(): void` — confronta l'header `X-Api-Key` con `hash_equals`, termina con `401` se non corrisponde.
  - `utc_now_mysql(): string` — data/ora corrente UTC in formato `Y-m-d H:i:s` (per scrivere `created_at`).
  - `to_iso8601_utc(string $mysql_datetime): string` — converte un `created_at` letto dal DB in formato ISO8601 `Y-m-d\TH:i:s\Z` (per le risposte JSON, compatibile con `new Date(...)` nel frontend).
- Produce (`message.php`): endpoint `POST /message.php`, contratto identico a quello Flask attuale (`{"text": "..."}` → `202 {"ok": true, "id": ..., "createdAt": ...}` o `400`/`413`/`429`).

- [ ] **Step 1: Scrivi `db.php`**

```php
<?php
// hosting/api/db.php

function get_config(): array
{
    $config_path = __DIR__ . '/config.php';
    if (!file_exists($config_path)) {
        http_response_code(500);
        header('Content-Type: application/json');
        error_log('config.php mancante: copiare config.php.example e compilarlo');
        echo json_encode(['error' => 'Errore di configurazione del server']);
        exit;
    }
    return require $config_path;
}

function get_db(): PDO
{
    $config = get_config();
    $dsn = sprintf(
        'mysql:host=%s;dbname=%s;charset=utf8mb4',
        $config['db_host'],
        $config['db_name']
    );

    try {
        return new PDO($dsn, $config['db_user'], $config['db_pass'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    } catch (PDOException $e) {
        http_response_code(500);
        header('Content-Type: application/json');
        error_log('Connessione al DB fallita: ' . $e->getMessage());
        echo json_encode(['error' => 'Errore di connessione al database']);
        exit;
    }
}

function require_api_key(): void
{
    $config = get_config();
    $chiave_fornita = $_SERVER['HTTP_X_API_KEY'] ?? '';

    if (!hash_equals($config['api_key'], $chiave_fornita)) {
        http_response_code(401);
        header('Content-Type: application/json');
        echo json_encode(['error' => 'Non autorizzato']);
        exit;
    }
}

function utc_now_mysql(): string
{
    return (new DateTimeImmutable('now', new DateTimeZone('UTC')))->format('Y-m-d H:i:s');
}

function to_iso8601_utc(string $mysql_datetime): string
{
    $dt = DateTime::createFromFormat('Y-m-d H:i:s', $mysql_datetime, new DateTimeZone('UTC'));
    return $dt->format('Y-m-d\TH:i:s\Z');
}
```

- [ ] **Step 2: Scrivi `message.php`**

```php
<?php
// hosting/api/message.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

$config = get_config();
$db = get_db();

$LIMITE_BODY_BYTE = 64 * 1024;
$corpo_raw = file_get_contents('php://input');

if (strlen($corpo_raw) > $LIMITE_BODY_BYTE) {
    http_response_code(413);
    echo json_encode(['error' => 'Corpo della richiesta troppo grande']);
    exit;
}

$corpo = json_decode($corpo_raw, true);

if (!is_array($corpo) || !isset($corpo['text']) || !is_string($corpo['text'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "text" è obbligatorio']);
    exit;
}

$testo = trim($corpo['text']);

if ($testo === '') {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "text" è obbligatorio']);
    exit;
}

if (mb_strlen($testo) > 1000) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "text" supera il limite di 1000 caratteri']);
    exit;
}

$ip = $_SERVER['REMOTE_ADDR'] ?? '';
$finestra_da = gmdate(
    'Y-m-d H:i:s',
    time() - $config['rate_limit_finestra_minuti'] * 60
);

$conteggio_stmt = $db->prepare(
    'SELECT COUNT(*) FROM messaggi WHERE ip = :ip AND created_at >= :da'
);
$conteggio_stmt->execute(['ip' => $ip, 'da' => $finestra_da]);
$conteggio = (int) $conteggio_stmt->fetchColumn();

if ($conteggio >= $config['rate_limit_max_messaggi']) {
    http_response_code(429);
    echo json_encode(['error' => 'Troppi messaggi inviati, riprova tra qualche minuto']);
    exit;
}

$created_at_db = utc_now_mysql();

$insert_stmt = $db->prepare(
    'INSERT INTO messaggi (text, created_at, status, ip) VALUES (:text, :created_at, "pending", :ip)'
);
$insert_stmt->execute(['text' => $testo, 'created_at' => $created_at_db, 'ip' => $ip]);

http_response_code(202);
echo json_encode([
    'ok' => true,
    'id' => (int) $db->lastInsertId(),
    'createdAt' => to_iso8601_utc($created_at_db),
]);
```

- [ ] **Step 3: Verifica manuale**

Con `config.php` compilato (Task 1) e un database raggiungibile, avvia il server di sviluppo PHP dalla cartella `hosting/api`:

```bash
cd hosting/api && php -S localhost:8000
```

In un altro terminale:

```bash
curl -i -X POST http://localhost:8000/message.php \
  -H "Content-Type: application/json" \
  -d '{"text": "ciao mondo"}'
```

Expected: `HTTP/1.1 202 Accepted` con corpo `{"ok":true,"id":1,"createdAt":"..."}`. Verifica poi con il client MySQL che la riga sia stata inserita con `status='pending'`.

```bash
curl -i -X POST http://localhost:8000/message.php \
  -H "Content-Type: application/json" \
  -d '{"text": "   "}'
```

Expected: `HTTP/1.1 400 Bad Request`.

Ripeti la prima chiamata altre 5 volte di seguito: dalla sesta in poi expected `HTTP/1.1 429 Too Many Requests` (con i valori di default `rate_limit_max_messaggi=5`).

```bash
curl -i -X POST http://localhost:8000/message.php \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$(python3 -c 'print("a" * 70000)')\"}"
```

Expected: `HTTP/1.1 413 Payload Too Large`.

- [ ] **Step 4: Commit**

```bash
git add hosting/api/db.php hosting/api/message.php
git commit -m "feat: aggiungi db.php e endpoint POST /message.php con rate limit per IP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Endpoint `history.php`

**Files:**
- Create: `hosting/api/history.php`

**Interfaces:**
- Consuma: `get_db()` e `to_iso8601_utc()` da `hosting/api/db.php` (Task 2).
- Produce: endpoint `GET /history.php?limit=&offset=`, contratto identico a quello Flask attuale (`{"messaggi": [...]}`, con `limit` vincolato in `[1, 100]` e `offset` vincolato a `>= 0`). Non espone mai la colonna `ip`.

- [ ] **Step 1: Scrivi `history.php`**

```php
<?php
// hosting/api/history.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

$db = get_db();

$limit = isset($_GET['limit']) ? (int) $_GET['limit'] : 10;
$offset = isset($_GET['offset']) ? (int) $_GET['offset'] : 0;

$limit = max(1, min($limit, 100));
$offset = max(0, $offset);

$stmt = $db->prepare(
    'SELECT id, text, created_at, status FROM messaggi
     WHERE status = "delivered"
     ORDER BY id DESC
     LIMIT :limit OFFSET :offset'
);
$stmt->bindValue(':limit', $limit, PDO::PARAM_INT);
$stmt->bindValue(':offset', $offset, PDO::PARAM_INT);
$stmt->execute();
$righe = $stmt->fetchAll();

$messaggi = array_map(function ($riga) {
    return [
        'id' => (int) $riga['id'],
        'text' => $riga['text'],
        'created_at' => to_iso8601_utc($riga['created_at']),
        'status' => $riga['status'],
    ];
}, $righe);

echo json_encode(['messaggi' => $messaggi]);
```

- [ ] **Step 2: Verifica manuale**

Con il server già avviato (`php -S localhost:8000` dentro `hosting/api`, vedi Task 2) e almeno un messaggio marcato `delivered` nel DB di test (`UPDATE messaggi SET status='delivered' WHERE id=1;`):

```bash
curl -i "http://localhost:8000/history.php?limit=1&offset=0"
```

Expected: `HTTP/1.1 200 OK` con `{"messaggi":[{"id":1,"text":"ciao mondo","created_at":"...","status":"delivered"}]}` — nessuna chiave `ip` nella risposta.

```bash
curl -i "http://localhost:8000/history.php?limit=-1&offset=-5"
```

Expected: `200 OK`, nessun errore (limit/offset vincolati internamente).

- [ ] **Step 3: Commit**

```bash
git add hosting/api/history.php
git commit -m "feat: aggiungi endpoint GET /history.php

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Endpoint privato `claim.php`

**Files:**
- Create: `hosting/api/claim.php`

**Interfaces:**
- Consuma: `require_api_key()` e `get_db()` da `hosting/api/db.php` (Task 2).
- Produce: endpoint `POST /claim.php` (richiede header `X-Api-Key`), usato dal Pi (Task 7). Risponde `204` senza corpo se non c'è nulla da stampare, `200 {"id": ..., "text": ...}` se reclama un messaggio (e lo marca `status='printing'`), `401` senza chiave valida.

- [ ] **Step 1: Scrivi `claim.php`**

```php
<?php
// hosting/api/claim.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

require_api_key();

$db = get_db();
$db->beginTransaction();

try {
    $stmt = $db->prepare(
        'SELECT id, text FROM messaggi WHERE status = "pending" ORDER BY id ASC LIMIT 1 FOR UPDATE'
    );
    $stmt->execute();
    $riga = $stmt->fetch();

    if ($riga === false) {
        $db->commit();
        http_response_code(204);
        exit;
    }

    $update_stmt = $db->prepare('UPDATE messaggi SET status = "printing" WHERE id = :id');
    $update_stmt->execute(['id' => $riga['id']]);

    $db->commit();

    http_response_code(200);
    echo json_encode(['id' => (int) $riga['id'], 'text' => $riga['text']]);
} catch (Exception $e) {
    $db->rollBack();
    http_response_code(500);
    error_log('Errore durante il claim: ' . $e->getMessage());
    echo json_encode(['error' => 'Errore interno']);
}
```

- [ ] **Step 2: Verifica manuale**

Con il server avviato e `config.php` compilato con una `api_key` nota, inserisci un messaggio pending (`curl` su `message.php`, Task 2), poi:

```bash
curl -i -X POST http://localhost:8000/claim.php
```

Expected: `HTTP/1.1 401 Unauthorized` (nessuna chiave).

```bash
curl -i -X POST http://localhost:8000/claim.php -H "X-Api-Key: LA_TUA_CHIAVE"
```

Expected (primo messaggio pending presente): `HTTP/1.1 200 OK` con `{"id":...,"text":"..."}`. Verifica con il client MySQL che quella riga sia ora `status='printing'`.

Ripeti la stessa chiamata: expected `HTTP/1.1 204 No Content` (nessun altro messaggio pending).

- [ ] **Step 3: Commit**

```bash
git add hosting/api/claim.php
git commit -m "feat: aggiungi endpoint privato POST /claim.php con claim atomico

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Endpoint privato `ack.php`

**Files:**
- Create: `hosting/api/ack.php`

**Interfaces:**
- Consuma: `require_api_key()` e `get_db()` da `hosting/api/db.php` (Task 2).
- Produce: endpoint `POST /ack.php` (richiede header `X-Api-Key`, body `{"id": <int>}`), usato dal Pi (Task 7). Risponde `200 {"ok": true}` solo se la riga era in stato `printing` (e la marca `delivered`), altrimenti `404`.

- [ ] **Step 1: Scrivi `ack.php`**

```php
<?php
// hosting/api/ack.php

require __DIR__ . '/db.php';

header('Content-Type: application/json');

require_api_key();

$db = get_db();

$corpo = json_decode(file_get_contents('php://input'), true);

if (!is_array($corpo) || !isset($corpo['id']) || !is_int($corpo['id'])) {
    http_response_code(400);
    echo json_encode(['error' => 'Il campo "id" è obbligatorio']);
    exit;
}

$stmt = $db->prepare(
    'UPDATE messaggi SET status = "delivered" WHERE id = :id AND status = "printing"'
);
$stmt->execute(['id' => $corpo['id']]);

if ($stmt->rowCount() === 0) {
    http_response_code(404);
    echo json_encode(['error' => 'Messaggio non trovato o non in stato printing']);
    exit;
}

http_response_code(200);
echo json_encode(['ok' => true]);
```

- [ ] **Step 2: Verifica manuale**

Con un messaggio in stato `printing` (ottenuto reclamandolo via `claim.php`, Task 4), prendi il suo `id` e:

```bash
curl -i -X POST http://localhost:8000/ack.php \
  -H "X-Api-Key: LA_TUA_CHIAVE" \
  -H "Content-Type: application/json" \
  -d '{"id": 1}'
```

Expected: `HTTP/1.1 200 OK` con `{"ok":true}`. Verifica con il client MySQL che la riga sia ora `status='delivered'`.

Ripeti la stessa chiamata (l'id è ora `delivered`, non più `printing`):

```bash
curl -i -X POST http://localhost:8000/ack.php \
  -H "X-Api-Key: LA_TUA_CHIAVE" \
  -H "Content-Type: application/json" \
  -d '{"id": 1}'
```

Expected: `HTTP/1.1 404 Not Found`.

- [ ] **Step 3: Commit**

```bash
git add hosting/api/ack.php
git commit -m "feat: aggiungi endpoint privato POST /ack.php

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: README del backend PHP (deploy + checklist di test manuale)

**Files:**
- Create: `hosting/README.md`

**Interfaces:**
- Nessuna nuova interfaccia di codice: documenta l'uso dei 4 endpoint prodotti nei Task 2–5.

- [ ] **Step 1: Scrivi `hosting/README.md`**

```markdown
# hosting

Frontend statico (`frontend/index.html`, copiato qui in fase di deploy) e
backend PHP + MySQL, pensati per essere caricati sullo stesso hosting
condiviso (es. `mondoarotoli.cuoredinapoli.net`). Vedi la spec completa in
`../docs/superpowers/specs/2026-09-11-hosting-php-polling-design.md`.

## Deploy

1. Crea un database MySQL sull'hosting ed esegui `schema.sql` (via
   phpMyAdmin o client `mysql`).
2. Copia `api/config.php.example` in `api/config.php` sull'hosting e
   compilalo con le credenziali reali del database e una `api_key` generata
   con `php -r "echo bin2hex(random_bytes(32));"`. Questo file non va mai
   committato.
3. Carica la cartella `api/` (incluso il tuo `config.php`, escluso
   `config.php.example` se vuoi) sull'hosting.
4. Carica `frontend/index.html` nella root del sito.
5. Comunica la stessa `api_key` al Raspberry Pi (vedi `../backend/README.md`).

## Endpoint pubblici

- `POST /api/message.php` — body `{"text": "..."}` → `202`/`400`/`429`.
- `GET /api/history.php?limit=&offset=` → `200 {"messaggi": [...]}`.

## Endpoint privati (richiedono header `X-Api-Key`)

- `POST /api/claim.php` → `200 {"id", "text"}` o `204` se non c'è nulla da
  stampare, `401` senza chiave valida.
- `POST /api/ack.php` — body `{"id": ...}` → `200 {"ok": true}` o `404` se
  l'id non è in stato `printing`.

## Checklist di test manuale end-to-end

Dopo il deploy, verifica nell'ordine (sostituendo l'URL con quello reale):

1. `curl -i -X POST https://TUO_DOMINIO/api/message.php -H "Content-Type: application/json" -d '{"text": "test"}'` → `202`.
2. `curl -i -X POST https://TUO_DOMINIO/api/claim.php -H "X-Api-Key: TUA_CHIAVE"` → `200` con il messaggio appena inviato.
3. `curl -i -X POST https://TUO_DOMINIO/api/ack.php -H "X-Api-Key: TUA_CHIAVE" -H "Content-Type: application/json" -d '{"id": ID_RESTITUITO_SOPRA}'` → `200 {"ok": true}`.
4. `curl -i "https://TUO_DOMINIO/api/history.php"` → `200` con il messaggio ora presente.
5. Ripeti il punto 1 sei volte di fila dallo stesso IP: la sesta chiamata deve rispondere `429`.

## Sblocco manuale di un messaggio bloccato in `printing`

Se il Raspberry Pi si interrompe tra un claim riuscito e la conferma (ack),
il messaggio resta in stato `printing` **per scelta**: non c'è uno sblocco
automatico, per evitare il rischio di stampare due volte lo stesso
messaggio. Se sei sicuro che il messaggio NON sia stato effettivamente
stampato, sbloccalo a mano:

```sql
UPDATE messaggi SET status = 'pending' WHERE id = ...;
```

Esegui questo comando solo dopo aver verificato fisicamente che la stampa
non sia avvenuta.
```

- [ ] **Step 2: Commit**

```bash
git add hosting/README.md
git commit -m "docs: aggiungi README di deploy e checklist di test per il backend PHP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Client HTTP Python (`api_client.py`)

**Files:**
- Create: `backend/api_client.py`
- Test: `backend/tests/test_api_client.py`
- Modify: `backend/requirements.txt`

**Interfaces:**
- Consuma: il contratto HTTP di `claim.php`/`ack.php` (Task 4, Task 5): `POST claim.php` → `204` o `200 {"id", "text"}`; `POST ack.php` con body `{"id"}` → `200` o `404`.
- Produce (usato da `poller.py`, Task 8):
  - `reclama_messaggio(base_url: str, api_key: str) -> dict | None`
  - `conferma_messaggio(base_url: str, api_key: str, message_id: int) -> bool`

- [ ] **Step 1: Scrivi il test**

```python
# backend/tests/test_api_client.py
import api_client


class RispostaFinta:
    def __init__(self, status_code, corpo=None):
        self.status_code = status_code
        self._corpo = corpo

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_reclama_messaggio_ritorna_none_se_204(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(204))

    risultato = api_client.reclama_messaggio("http://esempio", "chiave")

    assert risultato is None


def test_reclama_messaggio_ritorna_messaggio_se_200(monkeypatch):
    corpo = {"id": 1, "text": "ciao"}
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(200, corpo))

    risultato = api_client.reclama_messaggio("http://esempio", "chiave")

    assert risultato == corpo


def test_reclama_messaggio_passa_la_api_key_nell_header(monkeypatch):
    chiamate = []

    def post_finto(url, headers=None, timeout=None, **kwargs):
        chiamate.append((url, headers))
        return RispostaFinta(204)

    monkeypatch.setattr(api_client.requests, "post", post_finto)

    api_client.reclama_messaggio("http://esempio", "segreta")

    assert chiamate[0][1]["X-Api-Key"] == "segreta"


def test_conferma_messaggio_ritorna_true_se_200(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(200))

    assert api_client.conferma_messaggio("http://esempio", "chiave", 1) is True


def test_conferma_messaggio_ritorna_false_se_404(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(404))

    assert api_client.conferma_messaggio("http://esempio", "chiave", 1) is False
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && pytest tests/test_api_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'api_client'`.

- [ ] **Step 3: Aggiungi `requests` alle dipendenze**

Apri `backend/requirements.txt` e aggiungi in fondo:

```
requests
```

Installa le dipendenze aggiornate:

```bash
cd backend && source venv/bin/activate && pip install -r requirements-dev.txt
```

- [ ] **Step 4: Scrivi `api_client.py`**

```python
# backend/api_client.py
import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDI = 10


def reclama_messaggio(base_url, api_key):
    """Chiama POST /claim.php. Ritorna un dict {"id": ..., "text": ...} se
    c'e' un messaggio da stampare, altrimenti None."""
    risposta = requests.post(
        f"{base_url}/claim.php",
        headers={"X-Api-Key": api_key},
        timeout=TIMEOUT_SECONDI,
    )

    if risposta.status_code == 204:
        return None

    risposta.raise_for_status()
    return risposta.json()


def conferma_messaggio(base_url, api_key, message_id):
    """Chiama POST /ack.php. Ritorna True se il messaggio e' stato
    confermato, False se il server risponde 404 (gia' confermato o
    inesistente)."""
    risposta = requests.post(
        f"{base_url}/ack.php",
        headers={"X-Api-Key": api_key},
        json={"id": message_id},
        timeout=TIMEOUT_SECONDI,
    )

    if risposta.status_code == 404:
        return False

    risposta.raise_for_status()
    return True
```

- [ ] **Step 5: Esegui i test e verifica che passino**

Run: `cd backend && pytest tests/test_api_client.py -v`
Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add backend/api_client.py backend/tests/test_api_client.py backend/requirements.txt
git commit -m "feat: aggiungi client HTTP per claim/ack verso il backend PHP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 8: Loop di polling (`poller.py`)

**Files:**
- Create: `backend/poller.py`
- Test: `backend/tests/test_poller.py`

**Interfaces:**
- Consuma: `api_client.reclama_messaggio(base_url, api_key) -> dict | None` e `api_client.conferma_messaggio(base_url, api_key, message_id) -> bool` (Task 7); `printer.stampa_messaggio(stampante, testo) -> bool` e `printer.get_printer()` (esistenti, invariati).
- Produce:
  - `process_one_ciclo(base_url, api_key, stampante) -> None` — un singolo ciclo (claim → eventuale stampa → eventuale ack), non solleva mai eccezioni.
  - `poller_loop(base_url, api_key, stampante) -> None` — loop infinito che chiama `process_one_ciclo` ogni `INTERVALLO_SECONDI` (5) secondi.

- [ ] **Step 1: Scrivi il test**

```python
# backend/tests/test_poller.py
import poller


class StampanteFinta:
    def __init__(self, fallisce=False):
        self.fallisce = fallisce
        self.testi_stampati = []

    def set(self, **kwargs):
        pass

    def text(self, testo):
        pass

    def image(self, immagine):
        if self.fallisce:
            raise RuntimeError("USB scollegata")
        self.testi_stampati.append(immagine)


def test_process_one_ciclo_non_fa_nulla_se_nessun_messaggio(monkeypatch):
    monkeypatch.setattr(poller.api_client, "reclama_messaggio", lambda *a, **k: None)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)

    assert stampante.testi_stampati == []


def test_process_one_ciclo_stampa_e_conferma(monkeypatch):
    conferme = []
    monkeypatch.setattr(
        poller.api_client, "reclama_messaggio", lambda *a, **k: {"id": 1, "text": "ciao"}
    )
    monkeypatch.setattr(
        poller.api_client,
        "conferma_messaggio",
        lambda base_url, api_key, message_id: conferme.append(message_id) or True,
    )
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)

    assert len(stampante.testi_stampati) == 1
    assert conferme == [1]


def test_process_one_ciclo_non_conferma_se_la_stampa_fallisce(monkeypatch):
    chiamato = []
    monkeypatch.setattr(
        poller.api_client, "reclama_messaggio", lambda *a, **k: {"id": 1, "text": "ciao"}
    )
    monkeypatch.setattr(
        poller.api_client, "conferma_messaggio", lambda *a, **k: chiamato.append(True)
    )
    stampante = StampanteFinta(fallisce=True)

    poller.process_one_ciclo("http://esempio", "chiave", stampante)

    assert chiamato == []


def test_process_one_ciclo_gestisce_errore_di_rete_durante_il_claim(monkeypatch):
    def claim_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(poller.api_client, "reclama_messaggio", claim_rotto)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)  # non deve sollevare

    assert stampante.testi_stampati == []


def test_process_one_ciclo_gestisce_errore_di_rete_durante_l_ack(monkeypatch):
    monkeypatch.setattr(
        poller.api_client, "reclama_messaggio", lambda *a, **k: {"id": 1, "text": "ciao"}
    )

    def ack_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(poller.api_client, "conferma_messaggio", ack_rotto)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)  # non deve sollevare

    assert len(stampante.testi_stampati) == 1
```

- [ ] **Step 2: Esegui i test e verifica che falliscano**

Run: `cd backend && pytest tests/test_poller.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'poller'`.

- [ ] **Step 3: Scrivi `poller.py`**

```python
# backend/poller.py
import logging
import os
import time

import api_client
import printer as printer_module

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 5


def process_one_ciclo(base_url, api_key, stampante):
    try:
        messaggio = api_client.reclama_messaggio(base_url, api_key)
    except Exception:
        logger.exception("Errore durante il claim del messaggio")
        return

    if messaggio is None:
        return

    riuscito = printer_module.stampa_messaggio(stampante, messaggio["text"])

    if not riuscito:
        logger.error(
            "Stampa fallita per il messaggio %s, resta in stato 'printing' "
            "(richiede sblocco manuale, vedi hosting/README.md)",
            messaggio["id"],
        )
        return

    try:
        confermato = api_client.conferma_messaggio(base_url, api_key, messaggio["id"])
        if not confermato:
            logger.error(
                "Ack rifiutato dal server per il messaggio %s "
                "(gia' confermato o non trovato)",
                messaggio["id"],
            )
    except Exception:
        logger.exception(
            "Errore di rete durante l'ack del messaggio %s; il messaggio resta "
            "in stato 'printing' e non verra' ristampato automaticamente",
            messaggio["id"],
        )


def poller_loop(base_url, api_key, stampante):
    while True:
        try:
            process_one_ciclo(base_url, api_key, stampante)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di polling")
        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    base_url = os.environ["API_BASE_URL"]
    api_key = os.environ["API_KEY"]

    stampante = printer_module.get_printer()
    poller_loop(base_url, api_key, stampante)
```

- [ ] **Step 4: Esegui i test e verifica che passino**

Run: `cd backend && pytest tests/test_poller.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/poller.py backend/tests/test_poller.py
git commit -m "feat: aggiungi poller.py, loop di polling ogni 5s verso il backend PHP

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: Rimuovi i file obsoleti del Pi e aggiorna systemd/README

**Files:**
- Delete: `backend/app.py`, `backend/db.py`, `backend/worker.py`, `backend/schema.sql`
- Delete: `backend/tests/test_app.py`, `backend/tests/test_db.py`, `backend/tests/test_worker.py`
- Modify: `backend/requirements.txt`
- Modify: `backend/txtinstallazione.service`
- Modify: `backend/README.md`
- Modify: `.gitignore`

**Interfaces:**
- Nessuna nuova interfaccia: rimuove il codice del vecchio server Flask/SQLite ormai sostituito da `poller.py` + `api_client.py` (Task 7-8), e aggiorna configurazione/documentazione di conseguenza.

- [ ] **Step 1: Rimuovi i file Python obsoleti e i relativi test**

```bash
cd backend
git rm app.py db.py worker.py schema.sql
git rm tests/test_app.py tests/test_db.py tests/test_worker.py
```

- [ ] **Step 2: Aggiorna `requirements.txt`**

Sostituisci il contenuto di `backend/requirements.txt` (rimuove Flask/Flask-CORS, non più necessari senza un server HTTP sul Pi):

```
Pillow
python-escpos
requests
```

- [ ] **Step 3: Aggiorna `txtinstallazione.service`**

Sostituisci il contenuto di `backend/txtinstallazione.service`:

```ini
[Unit]
Description=txtinstallazione poller
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/pi/txtinstallazione
EnvironmentFile=/home/pi/txtinstallazione/.env
ExecStart=/home/pi/txtinstallazione/venv/bin/python3 /home/pi/txtinstallazione/poller.py
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Aggiungi `.env` al `.gitignore`**

Apri `.gitignore` e aggiungi in fondo:

```
backend/.env
```

- [ ] **Step 5: Aggiorna `backend/README.md`**

Sostituisci il contenuto di `backend/README.md`:

```markdown
# backend

Client Python che gira sul Raspberry Pi Zero: ogni 5 secondi interroga il
backend PHP dell'hosting (`hosting/api/claim.php`) per un nuovo messaggio,
lo stampa sulla stampante USB collegata e conferma la stampa
(`hosting/api/ack.php`). Non espone alcun server HTTP: il Pi non deve mai
essere raggiungibile da internet.

Sostituisce il precedente server Flask + SQLite locale. Vedi la spec
completa in
`../docs/superpowers/specs/2026-09-11-hosting-php-polling-design.md`.

## Configurazione

Crea un file `.env` (non committato, vedi `.gitignore`) nella cartella
`backend/` con:

```
API_BASE_URL=https://TUO_DOMINIO/api
API_KEY=la_stessa_chiave_configurata_in_hosting/api/config.php
```

## Sviluppo locale

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Avvio sul Raspberry Pi

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)
python3 poller.py
```

## Esecuzione in produzione (systemd)

L'avvio manuale sopra è utile per sviluppo e debug, ma non sopravvive alla
chiusura della sessione SSH o a un riavvio del Pi. Per la produzione,
usare il servizio systemd incluso (`txtinstallazione.service`), che legge
le variabili da `.env` e riavvia automaticamente il processo in caso di
crash:

```bash
sudo cp txtinstallazione.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now txtinstallazione
```

Il file assume che il progetto sia clonato in `/home/pi/txtinstallazione`
con il virtualenv in `venv/` e il file `.env` nella stessa cartella;
adattare i percorsi nel file `.service` se diversi. Log del servizio:
`journalctl -u txtinstallazione -f`.

## Messaggi bloccati in stato "printing"

Se il poller si interrompe tra un claim riuscito e la conferma, un
messaggio può restare bloccato in stato `printing` sull'hosting. Questo è
voluto (evita il rischio di doppie stampe): vedi
`../hosting/README.md` per la procedura di sblocco manuale.
```

- [ ] **Step 6: Esegui l'intera suite di test per confermare che non ci siano riferimenti rotti**

Run: `cd backend && pytest -v`
Expected: tutti i test passano (rimangono solo `test_printer.py`, `test_api_client.py`, `test_poller.py`).

- [ ] **Step 7: Commit**

```bash
git add backend/requirements.txt backend/txtinstallazione.service backend/README.md .gitignore
git commit -m "refactor: rimuovi Flask/SQLite dal Pi, sostituiti da poller.py

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: Aggiorna il frontend per puntare ai nuovi endpoint

**Files:**
- Modify: `frontend/index.html:332`
- Modify: `frontend/index.html:386` (path `/message/history` → `/history.php`)
- Modify: `frontend/index.html:442` (path `/message` → `/message.php`)

**Interfaces:**
- Consuma: gli endpoint pubblici `POST /api/message.php` e `GET /api/history.php` (Task 2, Task 3).

- [ ] **Step 1: Aggiorna `API_URL` a un path relativo (stessa origine dell'hosting)**

In `frontend/index.html`, sostituisci:

```javascript
const API_URL = 'https://txtinstallazione.info-cuoredinapoli.workers.dev';
```

con:

```javascript
const API_URL = '/api';
```

- [ ] **Step 2: Aggiorna la chiamata allo storico**

Sostituisci:

```javascript
const risposta = await fetch(`${API_URL}/message/history?limit=${BATCH_STORICO}&offset=${offsetStorico}`);
```

con:

```javascript
const risposta = await fetch(`${API_URL}/history.php?limit=${BATCH_STORICO}&offset=${offsetStorico}`);
```

- [ ] **Step 3: Aggiorna la chiamata di invio**

Sostituisci:

```javascript
const risposta = await fetch(`${API_URL}/message`, {
```

con:

```javascript
const risposta = await fetch(`${API_URL}/message.php`, {
```

- [ ] **Step 4: Verifica manuale end-to-end**

Con i file PHP del Task 2-5 serviti localmente su `php -S localhost:8000` dentro una cartella `api/` accanto a `index.html` (struttura identica a quella di deploy: `index.html` nella root, `api/` come sottocartella), apri `index.html` nel browser puntato su `http://localhost:8000/`, scrivi un messaggio, invia, e verifica che:
- la richiesta di invio vada a `http://localhost:8000/api/message.php` (controllo nel pannello Network del browser) e risponda `202`;
- lo storico si aggiorni chiamando `http://localhost:8000/api/history.php`.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat: aggiorna il frontend per puntare agli endpoint PHP sullo stesso hosting

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

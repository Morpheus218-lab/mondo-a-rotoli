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

- `POST /api/message.php` — body `{"text": "..."}` → `202`/`400`/`413`/`429`.
- `GET /api/history.php?limit=&offset=` → `200 {"messaggi": [...]}` (ogni
  messaggio include anche `likes`, il numero di "mi piace" ricevuti).
- `POST /api/like.php` — body `{"id": ...}` → `200`/`400`/`404`/`429`.
  - `200 {"likes": <nuovo_totale>}`: like registrato.
  - `400`: campo `id` mancante o non intero.
  - `404`: messaggio non trovato o non ancora in stato `delivered` (non
    ha senso mettere like a un messaggio non ancora stampato).
  - `429`: troppi like dallo stesso IP nella finestra di tempo
    configurata (`rate_limit_max_like`/`rate_limit_finestra_like_minuti`
    in `config.php`, di default 30 ogni 2 minuti). Solo aggiunta: non
    esiste un modo per togliere un like già dato.

## Endpoint privati (richiedono header `X-Api-Key`)

- `POST /api/claim.php` → `200 {"id", "text"}` o `204` se non c'è nulla da
  stampare, `401` senza chiave valida.
- `POST /api/ack.php` — body `{"id": ...}` → `200`/`400`/`401`/`404`.
  - `200`: messaggio confermato e spostato a `delivered`.
  - `400`: campo `id` mancante o non intero.
  - `401`: header `X-Api-Key` mancante o invalido.
  - `404`: messaggio non trovato o non in stato `printing`.

## Migrazione: aggiungere i "mi piace" a un database già in produzione

Se hai già eseguito `schema.sql` in passato (il sito è già online), la
tabella `messaggi` non ha ancora la colonna `likes` né esiste
`like_eventi`. Esegui una volta, a mano (phpMyAdmin o client `mysql`):

```sql
ALTER TABLE messaggi ADD COLUMN likes INT NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS like_eventi (
  id INT AUTO_INCREMENT PRIMARY KEY,
  message_id INT NOT NULL,
  ip VARCHAR(45) NOT NULL,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB;

CREATE INDEX idx_like_eventi_ip_created_at ON like_eventi (ip, created_at);
```

Se il database esisteva già anche prima di questo, aggiungi anche l'indice
usato dal nuovo ordinamento per data (invece che per id) in
`history.php`:

```sql
CREATE INDEX idx_messaggi_status_created_at ON messaggi (status, created_at);
```

Poi aggiungi anche a `config.php` (non nel `.example`, in quello reale
già sull'hosting) le due nuove righe `rate_limit_max_like` e
`rate_limit_finestra_like_minuti` — vedi `config.php.example` per i
valori di default.

## Checklist di test manuale end-to-end

Dopo il deploy, verifica nell'ordine (sostituendo l'URL con quello reale):

1. `curl -i -X POST https://TUO_DOMINIO/api/message.php -H "Content-Type: application/json" -d '{"text": "test"}'` → `202`.
2. `curl -i -X POST https://TUO_DOMINIO/api/claim.php -H "X-Api-Key: TUA_CHIAVE"` → `200` con il messaggio appena inviato.
3. `curl -i -X POST https://TUO_DOMINIO/api/ack.php -H "X-Api-Key: TUA_CHIAVE" -H "Content-Type: application/json" -d '{"id": ID_RESTITUITO_SOPRA}'` → `200 {"ok": true}`.
4. `curl -i "https://TUO_DOMINIO/api/history.php"` → `200` con il messaggio ora presente.
5. Ripeti il punto 1 altre 5 volte di fila dallo stesso IP (il messaggio del punto 1 conta già nella finestra): la quinta ripetizione (sesta chiamata in totale) deve rispondere `429`.
6. `curl -i -X POST https://TUO_DOMINIO/api/claim.php` (nessun header) → `401`.
7. `curl -i -X POST https://TUO_DOMINIO/api/ack.php -H "X-Api-Key: sbagliata" -d '{"id": 1}'` → `401`.
8. `curl -i -X POST https://TUO_DOMINIO/api/like.php -H "Content-Type: application/json" -d '{"id": ID_DEL_PUNTO_3}'` → `200 {"likes": 1}` (usa l'id del messaggio confermato al punto 3, ormai `delivered`).
9. `curl -i -X POST https://TUO_DOMINIO/api/like.php -H "Content-Type: application/json" -d '{"id": 999999}'` → `404` (id inesistente o non ancora stampato).

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

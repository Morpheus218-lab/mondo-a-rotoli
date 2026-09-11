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
- `GET /api/history.php?limit=&offset=` → `200 {"messaggi": [...]}`.

## Endpoint privati (richiedono header `X-Api-Key`)

- `POST /api/claim.php` → `200 {"id", "text"}` o `204` se non c'è nulla da
  stampare, `401` senza chiave valida.
- `POST /api/ack.php` — body `{"id": ...}` → `200`/`400`/`401`/`404`.
  - `200`: messaggio confermato e spostato a `delivered`.
  - `400`: campo `id` mancante o non intero.
  - `401`: header `X-Api-Key` mancante o invalido.
  - `404`: messaggio non trovato o non in stato `printing`.

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

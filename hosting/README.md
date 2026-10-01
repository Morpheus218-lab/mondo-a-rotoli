# hosting

Frontend statico (`frontend/index.html`, copiato qui in fase di deploy) e
backend PHP + MySQL, pensati per essere caricati sullo stesso hosting
condiviso (es. `mondoarotoli.cuoredinapoli.net`). Vedi la spec completa in
`../docs/superpowers/specs/2026-09-11-hosting-php-polling-design.md` e,
per il fan-out su più stampanti,
`../docs/superpowers/specs/2026-10-01-stampa-fan-out-multistampante-design.md`.

## Deploy

1. Crea un database MySQL sull'hosting ed esegui `schema.sql` (via
   phpMyAdmin o client `mysql`).
2. Copia `api/config.php.example` in `api/config.php` sull'hosting e
   compilalo con le credenziali reali del database. Questo file non va mai
   committato.
3. Carica la cartella `api/` (incluso il tuo `config.php`, escluso
   `config.php.example` se vuoi) sull'hosting.
4. Carica `frontend/index.html` nella root del sito.

## Endpoint pubblici

- `POST /api/message.php` — body `{"text": "..."}` → `202`/`400`/`413`/`429`.
  Il messaggio viene inserito con `status='delivered'` e compare
  **subito** nello storico pubblico — non esiste più uno stato intermedio
  "in stampa": ogni Raspberry Pi stampante lo recupera e lo stampa per
  conto proprio (vedi `../backend/README.md`), indipendentemente dagli
  altri.
- `GET /api/history.php?limit=&offset=` → `200 {"messaggi": [...]}` (ogni
  messaggio include anche `likes`, il numero di "mi piace" ricevuti).
- `POST /api/like.php` — body `{"id": ...}` → `200`/`400`/`404`/`429`.
  - `200 {"likes": <nuovo_totale>}`: like registrato.
  - `400`: campo `id` mancante o non intero.
  - `404`: messaggio non trovato.
  - `429`: troppi like dallo stesso IP nella finestra di tempo
    configurata (`rate_limit_max_like`/`rate_limit_finestra_like_minuti`
    in `config.php`, di default 30 ogni 2 minuti). Solo aggiunta: non
    esiste un modo per togliere un like già dato.

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

## Migrazione: passaggio alla stampa fan-out su più stampanti

Prima di questo cambio, `claim.php`/`ack.php` facevano sì che **una sola**
stampante si prendesse in carico ogni messaggio (stato intermedio
`printing`). Quegli endpoint sono stati rimossi: `message.php` ora
inserisce direttamente con `status='delivered'`, e ogni Raspberry Pi
stampante recupera e stampa tutti i messaggi in autonomia (vedi
`../backend/README.md`).

Se il sito era già in produzione con la versione precedente, potrebbero
esserci righe rimaste bloccate in `pending` o `printing` da prima del
deploy di questo cambio. **Dopo** aver aggiornato e fatto ripartire
*tutti* i Raspberry Pi stampanti con il nuovo `poller.py` (ognuno fa un
primo avvio "silenzioso" che non stampa nulla di già esistente, vedi
`../backend/README.md`), sblocca quelle righe una volta sola:

```sql
UPDATE messaggi SET status = 'delivered' WHERE status IN ('pending', 'printing');
```

Farlo **prima** che tutti i Pi abbiano completato il primo avvio farebbe
assorbire silenziosamente quei messaggi nella baseline di qualcuno di
loro, che quindi non li stamperebbe mai (restano comunque visibili
online, essendo `delivered`).

## Checklist di test manuale end-to-end

Dopo il deploy, verifica nell'ordine (sostituendo l'URL con quello reale):

1. `curl -i -X POST https://TUO_DOMINIO/api/message.php -H "Content-Type: application/json" -d '{"text": "test"}'` → `202`.
2. `curl -i "https://TUO_DOMINIO/api/history.php"` → `200`, il messaggio del punto 1 è già presente (nessun passaggio intermedio da aspettare).
3. Ripeti il punto 1 altre 5 volte di fila dallo stesso IP (il messaggio del punto 1 conta già nella finestra): la quinta ripetizione (sesta chiamata in totale) deve rispondere `429`.
4. `curl -i -X POST https://TUO_DOMINIO/api/like.php -H "Content-Type: application/json" -d '{"id": ID_DEL_PUNTO_1}'` → `200 {"likes": 1}`.
5. `curl -i -X POST https://TUO_DOMINIO/api/like.php -H "Content-Type: application/json" -d '{"id": 999999}'` → `404` (id inesistente).

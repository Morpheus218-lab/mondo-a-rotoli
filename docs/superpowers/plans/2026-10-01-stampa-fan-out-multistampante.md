# Stampa fan-out su più stampanti indipendenti Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ogni Raspberry Pi stampante stampa in autonomia tutti i messaggi nuovi, senza competere con le altre per lo stesso messaggio; al primo avvio nessun Pi stampa messaggi già esistenti.

**Architecture:** `hosting/api/message.php` inserisce direttamente con `status='delivered'` (niente più `pending`/`printing` lato pubblico); `claim.php`/`ack.php` vengono rimossi. `backend/poller.py` viene riscritto sul modello già in produzione di `bridge/fetcher.py`: ogni Pi polla `GET /api/history.php`, tiene un file locale con l'insieme degli id già stampati, e stampa solo i messaggi mai visti — con la differenza che al primissimo avvio (file locale assente) registra tutto come "visto" senza stampare nulla.

**Tech Stack:** PHP + PDO (hosting, invariato), Python 3 + `requests` (Pi stampante), `pytest` per i test Python.

**Spec:** [docs/superpowers/specs/2026-10-01-stampa-fan-out-multistampante-design.md](../specs/2026-10-01-stampa-fan-out-multistampante-design.md)

## Global Constraints

- `message.php` inserisce sempre con `status='delivered'`, mai più `'pending'`.
- `claim.php` e `ack.php` vengono rimossi: nessun client li chiama più.
- Nessuna modifica allo schema MySQL (`hosting/schema.sql` resta invariato).
- Dedup sempre per **insieme di id già visti**, mai per "ultimo id" (un messaggio può arrivare con id più basso di uno già visto se la query lato server lo restituisce fuori dall'ordine di inserimento).
- Righe non leggibili come JSON nel file di stato locale vengono ignorate con un warning, senza bloccare la lettura delle righe successive.
- **Al primo avvio di un Pi (file di stato locale assente) non si stampa nulla**: tutti i messaggi trovati in quel momento vengono registrati come "visti" senza essere stampati. Vale anche per un Pi già esistente che riceve questo nuovo codice.
- Un messaggio viene registrato come "visto" solo dopo stampa riuscita. Se un messaggio fallisce, i successivi dello stesso ciclo non vengono stampati (si riprova tutti insieme al ciclo dopo, nello stesso ordine).
- `PRINTER_ID` è solo per i log, non influenza nessuna logica.

---

## Task 1: Hosting — `message.php` diretto a `delivered`, rimozione `claim.php`/`ack.php`

**Files:**
- Modify: `hosting/api/message.php`
- Delete: `hosting/api/claim.php`
- Delete: `hosting/api/ack.php`
- Modify: `hosting/api/db.php`
- Modify: `hosting/api/config.php.example`
- Modify: `hosting/README.md`

**Interfaces:**
- Nessuna interfaccia di codice condivisa con altri task (PHP, nessun import da testare); Task 2/3 consumano solo l'endpoint pubblico `GET /history.php`, già esistente e invariato.

Non esiste un framework di test automatico per il PHP in questo repo (scelta già presa nella spec precedente, vedi `hosting/README.md`): la verifica è manuale via `curl`, stesso stile già in uso.

- [ ] **Step 1: Cambia l'insert di `message.php` da `pending` a `delivered`**

In `hosting/api/message.php`, sostituisci:

```php
$insert_stmt = $db->prepare(
    'INSERT INTO messaggi (text, created_at, status, ip) VALUES (:text, :created_at, "pending", :ip)'
);
```

con:

```php
$insert_stmt = $db->prepare(
    'INSERT INTO messaggi (text, created_at, status, ip) VALUES (:text, :created_at, "delivered", :ip)'
);
```

- [ ] **Step 2: Rimuovi `claim.php` e `ack.php`**

```bash
git rm hosting/api/claim.php hosting/api/ack.php
```

- [ ] **Step 3: Rimuovi la funzione `require_api_key()` da `db.php`, ormai inutilizzata**

In `hosting/api/db.php`, elimina interamente questo blocco (era usato solo da `claim.php`/`ack.php`):

```php
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
```

- [ ] **Step 4: Rimuovi la riga `api_key` da `config.php.example`**

In `hosting/api/config.php.example`, elimina questa riga (e il commento sopra):

```php
    // Genera una stringa lunga e casuale, es: php -r "echo bin2hex(random_bytes(32));"
    'api_key' => 'genera-una-chiave-lunga-e-casuale-qui',
```

Il file risultante deve essere:

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
    'rate_limit_max_messaggi' => 5,
    'rate_limit_finestra_minuti' => 2,
    'rate_limit_max_like' => 30,
    'rate_limit_finestra_like_minuti' => 2,
];
```

- [ ] **Step 5: Riscrivi `hosting/README.md`**

Sostituisci l'intero contenuto del file con:

```markdown
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
```

- [ ] **Step 6: Verifica manuale (richiede un hosting reale configurato)**

Se hai un ambiente di test disponibile, esegui la checklist sopra. Se no
(ambiente di produzione, non vuoi testare lì prima del deploy
completo), annota che la verifica avverrà al momento del deploy reale —
non bloccare il resto del piano per questo.

- [ ] **Step 7: Commit**

```bash
git add hosting/api/message.php hosting/api/db.php hosting/api/config.php.example hosting/README.md
git commit -m "feat: message.php inserisce direttamente delivered, rimuovi claim.php/ack.php"
```

---

## Task 2: `backend/api_client.py` — recupero storico al posto di claim/ack

**Files:**
- Modify (sostituzione integrale): `backend/api_client.py`
- Modify (sostituzione integrale): `backend/tests/test_api_client.py`

**Interfaces:**
- Produces: `recupera_storico(base_url, limit=100) -> list[dict]`

- [ ] **Step 1: Scrivi il test che fallisce**

Sostituisci l'intero contenuto di `backend/tests/test_api_client.py` con:

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


def test_recupera_storico_ritorna_la_lista_messaggi(monkeypatch):
    messaggi = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]
    monkeypatch.setattr(
        api_client.requests, "get", lambda *a, **k: RispostaFinta(200, {"messaggi": messaggi})
    )

    risultato = api_client.recupera_storico("http://esempio")

    assert risultato == messaggi


def test_recupera_storico_passa_il_limit_nei_parametri(monkeypatch):
    chiamate = []

    def get_finto(url, params=None, timeout=None, **kwargs):
        chiamate.append((url, params))
        return RispostaFinta(200, {"messaggi": []})

    monkeypatch.setattr(api_client.requests, "get", get_finto)

    api_client.recupera_storico("http://esempio", limit=100)

    assert chiamate[0][1]["limit"] == 100
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_api_client.py -v`
Expected: FAIL — `AttributeError: module 'api_client' has no attribute 'recupera_storico'`

- [ ] **Step 3: Sostituisci l'implementazione**

Sostituisci l'intero contenuto di `backend/api_client.py` con:

```python
# backend/api_client.py
import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDI = 10


def recupera_storico(base_url, limit=100):
    """Chiama GET /history.php?limit=. Ritorna la lista di messaggi
    consegnati (dict con almeno id, text, created_at), piu' recenti
    prima (stesso ordine della risposta dell'API)."""
    risposta = requests.get(
        f"{base_url}/history.php",
        params={"limit": limit},
        timeout=TIMEOUT_SECONDI,
    )
    risposta.raise_for_status()
    return risposta.json()["messaggi"]
```

- [ ] **Step 4: Verifica che passino**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_api_client.py -v`
Expected: PASS (2 test)

- [ ] **Step 5: Commit**

```bash
git add backend/api_client.py backend/tests/test_api_client.py
git commit -m "feat: backend/api_client.py recupera lo storico invece di claim/ack"
```

---

## Task 3: `backend/poller.py` — dedup locale, niente stampa al primo avvio

**Files:**
- Modify (sostituzione integrale): `backend/poller.py`
- Modify (sostituzione integrale): `backend/tests/test_poller.py`
- Modify: `backend/README.md`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `api_client.recupera_storico(base_url, limit=100) -> list[dict]` (Task 2)
- Produces: `process_one_ciclo(base_url, stato_path, stampante)`, `poller_loop(base_url, stato_path, stampante)`

- [ ] **Step 1: Scrivi i test che falliscono**

Sostituisci l'intero contenuto di `backend/tests/test_poller.py` con:

```python
# backend/tests/test_poller.py
import json

import poller


class StampanteFinta:
    """Simula la stampante. fallisce_dalla_chiamata, se impostato, fa
    sollevare un'eccezione da quella chiamata a image() in poi (1-based):
    es. fallisce_dalla_chiamata=2 fa fallire la seconda stampa e le
    successive."""

    def __init__(self, fallisce_dalla_chiamata=None):
        self.fallisce_dalla_chiamata = fallisce_dalla_chiamata
        self.chiamate = 0
        self.testi_stampati = []

    def set(self, **kwargs):
        pass

    def text(self, testo):
        pass

    def image(self, immagine):
        self.chiamate += 1
        if self.fallisce_dalla_chiamata is not None and self.chiamate >= self.fallisce_dalla_chiamata:
            raise RuntimeError("USB scollegata")
        self.testi_stampati.append(immagine)


def leggi_id_nel_file(path):
    if not path.exists():
        return set()
    return {json.loads(riga)["id"] for riga in path.read_text(encoding="utf-8").splitlines() if riga}


def test_primo_avvio_non_stampa_nulla_e_segna_tutto_come_visto(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    storico = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert stampante.testi_stampati == []
    assert leggi_id_nel_file(stato_path) == {1, 2}


def test_dopo_il_primo_avvio_stampa_solo_i_messaggi_nuovi(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(json.dumps({"id": 1, "text": "salve"}) + "\n", encoding="utf-8")
    storico = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 1
    assert leggi_id_nel_file(stato_path) == {1, 2}


def test_non_scrive_nulla_se_non_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + json.dumps({"id": 2, "text": "b"}) + "\n",
        encoding="utf-8",
    )
    storico = [{"id": 2, "text": "b"}, {"id": 1, "text": "a"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert stampante.testi_stampati == []
    assert leggi_id_nel_file(stato_path) == {1, 2}


def test_se_un_messaggio_fallisce_i_successivi_non_vengono_stampati_in_questo_ciclo(
    tmp_path, monkeypatch
):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text("", encoding="utf-8")  # file gia' esistente: non e' il primo avvio
    storico = [{"id": 3, "text": "c"}, {"id": 2, "text": "b"}, {"id": 1, "text": "a"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta(fallisce_dalla_chiamata=2)  # fallisce sul messaggio id=2

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 1  # solo id=1 stampato
    assert leggi_id_nel_file(stato_path) == {1}  # id=2 e id=3 restano "nuovi"


def test_riprende_un_messaggio_arrivato_fuori_ordine(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + json.dumps({"id": 3, "text": "c"}) + "\n",
        encoding="utf-8",
    )
    storico = [
        {"id": 4, "text": "d"},
        {"id": 3, "text": "c"},
        {"id": 2, "text": "b"},
        {"id": 1, "text": "a"},
    ]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 2  # id=2 e id=4
    assert leggi_id_nel_file(stato_path) == {1, 2, 3, 4}


def test_gestisce_errore_di_rete_durante_il_recupero_dello_storico(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"

    def recupero_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(poller.api_client, "recupera_storico", recupero_rotto)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)  # non deve sollevare

    assert stampante.testi_stampati == []
    assert not stato_path.exists()
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_poller.py -v`
Expected: FAIL — i test chiamano `process_one_ciclo` con tre argomenti posizionali (`base_url, stato_path, stampante`) mentre la versione attuale ne accetta `(base_url, api_key, stampante)` e usa `api_client.reclama_messaggio`/`conferma_messaggio`, non `recupera_storico`: fallisce con `AttributeError: module 'poller.api_client' has no attribute 'recupera_storico'` o simile su ogni test.

- [ ] **Step 3: Sostituisci l'implementazione**

Sostituisci l'intero contenuto di `backend/poller.py` con:

```python
# backend/poller.py
import json
import logging
import os
import time

import api_client
import printer as printer_module

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 5
LIMITE_STORICO = 100


def _leggi_id_gia_visti(stato_path):
    """Ritorna l'insieme degli id gia' presenti in stato_path. Righe non
    leggibili come JSON vengono ignorate con un warning, senza bloccare
    la lettura delle righe successive."""
    if not os.path.exists(stato_path):
        return set()

    id_visti = set()
    with open(stato_path, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                id_visti.add(json.loads(riga)["id"])
            except (json.JSONDecodeError, KeyError):
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, stato_path)

    return id_visti


def _registra_visto(stato_path, messaggio):
    with open(stato_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")


def process_one_ciclo(base_url, stato_path, stampante):
    """Recupera lo storico e stampa i messaggi mai visti, uno alla volta
    in ordine di id. Al primo avvio (stato_path non esiste ancora) non
    stampa nulla: registra tutto come "visto" per partire da li' in poi.
    Un messaggio viene registrato solo dopo stampa riuscita; se uno
    fallisce, i successivi di questo stesso ciclo non vengono tentati
    (restano "nuovi" e si riprova tutti insieme al ciclo dopo)."""
    try:
        messaggi = api_client.recupera_storico(base_url, limit=LIMITE_STORICO)
    except Exception:
        logger.exception("Errore durante il recupero dello storico")
        return

    primo_avvio = not os.path.exists(stato_path)
    id_gia_visti = _leggi_id_gia_visti(stato_path)
    nuovi = [m for m in messaggi if m["id"] not in id_gia_visti]
    nuovi.sort(key=lambda m: m["id"])

    if not nuovi:
        return

    if primo_avvio:
        for messaggio in nuovi:
            _registra_visto(stato_path, messaggio)
        logger.info(
            "Primo avvio: %s messaggi gia' presenti segnati come visti senza stamparli",
            len(nuovi),
        )
        return

    for messaggio in nuovi:
        riuscito = printer_module.stampa_messaggio(stampante, messaggio["text"])
        if not riuscito:
            logger.error(
                "Stampa fallita per il messaggio %s, verra' ritentato al prossimo ciclo",
                messaggio["id"],
            )
            return
        _registra_visto(stato_path, messaggio)


def poller_loop(base_url, stato_path, stampante):
    while True:
        try:
            process_one_ciclo(base_url, stato_path, stampante)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di polling")
        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    printer_id = os.environ.get("PRINTER_ID", "")
    formato = (
        f"%(asctime)s [{printer_id}] %(levelname)s %(name)s: %(message)s"
        if printer_id
        else "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.basicConfig(level=logging.INFO, format=formato)

    base_url = os.environ["API_BASE_URL"]
    stato_path = os.environ.get("STATO_FILE", "stampati.jsonl")

    stampante = printer_module.get_printer()
    poller_loop(base_url, stato_path, stampante)
```

- [ ] **Step 4: Verifica che passino**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -v`
Expected: PASS (tutti i test di `backend/`, inclusi quelli invariati di `test_printer.py` e quelli aggiornati di Task 2)

- [ ] **Step 5: Aggiungi `backend/*.jsonl` a `.gitignore`**

In `.gitignore`, dopo la riga `ledwall/*.jsonl`, aggiungi:

```
backend/*.jsonl
```

- [ ] **Step 6: Riscrivi `backend/README.md`**

Sostituisci l'intero contenuto del file con:

```markdown
# backend

Client Python che gira su ogni Raspberry Pi con una stampante
collegata: ogni 5 secondi interroga lo storico pubblico dell'hosting
(`hosting/api/history.php`), stampa i messaggi che non ha ancora
stampato sulla stampante USB collegata, e tiene traccia in locale di
cosa ha già stampato. Non espone alcun server HTTP: il Pi non deve mai
essere raggiungibile da internet.

**Ogni Pi stampante è indipendente dalle altre**: se ci sono più Pi in
luoghi diversi, ciascuno stampa autonomamente tutti i messaggi nuovi,
senza competere con gli altri per lo stesso messaggio. Vedi la spec in
`../docs/superpowers/specs/2026-10-01-stampa-fan-out-multistampante-design.md`.

**Al primo avvio un Pi non stampa nulla di già esistente**: registra lo
storico trovato in quel momento come "già visto" senza stamparlo, e da
lì in poi stampa solo ciò che arriva dopo. Questo vale anche per un Pi
già esistente quando riceve questa nuova versione del codice (il file
di stato locale, descritto sotto, non esiste ancora per lui).

## Configurazione

Crea un file `.env` (non committato, vedi `.gitignore`) nella cartella
`backend/` con:

```
API_BASE_URL=https://TUO_DOMINIO/api
STATO_FILE=/home/pi/mondo-a-rotoli/backend/stampati.jsonl
PRINTER_ID=napoli
```

`STATO_FILE` è opzionale (default `stampati.jsonl`, risolto rispetto
alla working directory del processo — con il servizio systemd incluso
questa è la root del repository, non `backend/`: per questo conviene
usare un percorso assoluto invece di lasciare il default). `PRINTER_ID`
è opzionale e serve solo per distinguere questo Pi nei log quando ne
guardi più di uno insieme — non influisce su nessuna logica.

## Formato del file di stato

Una riga JSON per messaggio stampato, con gli stessi campi restituiti
da `history.php` (`id`, `text`, `created_at`, `status`, `likes`). Serve
sia da elenco di cosa è già stato stampato (dedup) sia da archivio
locale di quel Pi.

## Sviluppo locale

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Avvio sul Raspberry Pi

Prima di installare le dipendenze Python, installa la libreria di sistema
che serve alla stampa via USB (`pyusb`, incluso in `requirements.txt`, si
appoggia a questa libreria):

```bash
sudo apt-get update && sudo apt-get install -y libusb-1.0-0
```

Poi:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)
python3 poller.py
```

Se la stampa fallisce con un errore relativo ai permessi USB (es.
`USBError: [Errno 13] Access denied`) pur con `lsusb` che mostra il
device (`0416:5011`, lo stesso vendor/product ID usato in `printer.py`,
`Usb(0x0416, 0x5011, ...)`), serve una regola udev che dia all'utente
`pi` accesso al dispositivo:

```bash
sudo tee /etc/udev/rules.d/99-escpos-printer.rules <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="0416", ATTR{idProduct}=="5011", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
```

La regola si applica solo ai device creati dopo il reload: scollega e
ricollega il cavo USB della stampante (o riavvia il Pi) prima di
riprovare.

## Esecuzione in produzione (systemd)

L'avvio manuale sopra è utile per sviluppo e debug, ma non sopravvive alla
chiusura della sessione SSH o a un riavvio del Pi. Per la produzione,
usare il servizio systemd incluso (`mondo-a-rotoli.service`), che legge
le variabili da `.env` e riavvia automaticamente il processo in caso di
crash:

```bash
sudo cp mondo-a-rotoli.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mondo-a-rotoli
```

Il file assume che il repository sia clonato in `/home/pi/mondo-a-rotoli`
e il file `.env` si trovi in `/home/pi/mondo-a-rotoli/backend/.env`;
adattare i percorsi nel file `.service` se diversi. Log del servizio:
`journalctl -u mondo-a-rotoli -f`.

## Aggiungere un nuovo Pi stampante

Ripeti questa stessa procedura su ogni Raspberry Pi: clona il repo,
configura `.env` con lo stesso `API_BASE_URL` (e un `PRINTER_ID` diverso
per distinguerlo nei log), avvia il servizio. Il primo avvio non stampa
nulla di già esistente, come descritto sopra.

## Stampa fallita: ritentata automaticamente, nessuno sblocco manuale

Se la stampa di un messaggio fallisce (es. stampante scollegata), quel
messaggio non viene registrato come stampato: resta "nuovo" e viene
ritentato al ciclo successivo (ogni 5s), insieme a tutti i messaggi
successivi arrivati nel frattempo. Non serve nessuno sblocco manuale —
diversamente da come funzionava con `claim.php`/`ack.php`.

## Limite di `history.php`: 100 messaggi per chiamata

`history.php` restituisce al massimo 100 messaggi per chiamata (stesso
limite già noto per `bridge/`, vedi `bridge/README.md`): se un Pi resta
spento o irraggiungibile abbastanza a lungo da accumulare più di 100
messaggi nuovi nel frattempo, quelli più vecchi della finestra dei 100
più recenti non vengono recuperati retroattivamente da quel Pi — restano
comunque stampati dagli altri Pi che non hanno perso il giro, e visibili
online.
```

- [ ] **Step 7: Commit**

```bash
git add backend/poller.py backend/tests/test_poller.py backend/README.md .gitignore
git commit -m "feat: poller.py stampa in fan-out con dedup locale, niente stampa al primo avvio"
```

---

## Task 4: Allinea il README principale

**Files:**
- Modify: `README.md`

**Interfaces:** nessuna (solo documentazione).

- [ ] **Step 1: Riscrivi `README.md`**

Sostituisci l'intero contenuto del file con:

```markdown
# mondo-a-rotoli

Installazione interattiva: una pagina web dove le persone scrivono un
messaggio, che viene stampato su carta da una o più stampanti USB
collegate ad altrettanti Raspberry Pi.

## Come far partire l'installazione

Per accendere tutto servono due cose, in ordine: **mettere online il sito**
e **accendere ogni Raspberry Pi con la sua stampante collegata**.

### 1. Metti online il sito

- Carica il contenuto delle cartelle `frontend/` e `hosting/api/` sul tuo
  hosting (dominio unico, es. `mondoarotoli.cuoredinapoli.net`).
- Crea un database MySQL vuoto e importa lo schema che trovi in
  `hosting/schema.sql` (con phpMyAdmin basta aprirlo e premere "Esegui").
- Copia il file `hosting/api/config.php.example`, rinomina la copia in
  `config.php` e scrivici dentro le credenziali del database.
- Apri il sito nel browser: deve comparire la pagina con il campo per
  scrivere il messaggio.

Tutti i comandi passo per passo sono in [`hosting/README.md`](hosting/README.md).

### 2. Accendi ogni Raspberry Pi

Ripeti questi passaggi su **ogni** Pi stampante: ognuno stampa in
autonomia tutti i messaggi, senza bisogno di coordinarsi con gli altri.

- Collega la stampante al Pi via USB e controlla che ci sia carta.
- Sul Pi, crea un file chiamato `.env` dentro la cartella `backend/` e
  scrivici l'indirizzo del sito (facoltativo un nome per distinguere
  questo Pi nei log).
- Avvia il programma con `python3 poller.py`, oppure — meglio, così
  riparte da solo a ogni riavvio del Pi — attiva il servizio automatico
  descritto nel README del backend.
- Al primo avvio il Pi non stampa nulla dei messaggi già esistenti:
  solo da quel momento in poi stampa ciò che arriva di nuovo, ogni 5
  secondi.

Tutti i comandi passo per passo sono in [`backend/README.md`](backend/README.md).

### 3. Prova che funzioni

Scrivi un messaggio di prova dal sito: entro 5 secondi deve uscire da
**tutte** le stampanti collegate. Se non succede su una di loro,
controlla nell'ordine: quel Pi è acceso ed è connesso a internet, la
stampante è collegata e ha carta, `API_BASE_URL` nel suo `.env` è
corretto.

## Come funziona

Il sistema è diviso in due parti: l'hosting condiviso, e N Raspberry Pi
stampanti indipendenti fra loro.

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│   Hosting condiviso      │        │   Raspberry Pi stampante #1   │
│   (es. cuoredinapoli)    │        │   (a casa/studio, no IP       │
│                          │   ┌───►│    pubblico, dietro NAT)      │
│  frontend/index.html    │   │    │  backend/poller.py             │
│      (pagina statica)   │   │    │      │ ogni 5s, GET history.php│
│           │              │   │    │      ▼                        │
│           ▼              │   │    │  backend/printer.py            │
│  hosting/api/*.php      │   │    │      │                        │
│      + tabella MySQL    │───┤    │      ▼                        │
│                          │   │    │  stampante termica USB         │
│                          │   │    └──────────────────────────────┘
│                          │   │    ┌──────────────────────────────┐
│                          │   └───►│   Raspberry Pi stampante #2    │
│                          │        │   (stessa logica, in un altro  │
└─────────────────────────┘        │    luogo, indipendente dal #1) │
                                    └──────────────────────────────┘
```

1. Un visitatore scrive un messaggio su **`frontend/index.html`**, che lo
   invia con `POST` a **`hosting/api/message.php`**. Il messaggio finisce
   subito in una tabella MySQL con stato `delivered` e compare
   immediatamente nello storico pubblico (`hosting/api/history.php`,
   mostrato in `frontend/index.html`).
2. Ogni **Raspberry Pi stampante** non riceve mai richieste da internet —
   non è mai raggiungibile dall'esterno, il che evita di dover
   configurare port forwarding o un dominio per il Pi. È lui che, ogni 5
   secondi, chiama verso l'esterno **`hosting/api/history.php`** e
   confronta la risposta con un elenco che tiene in locale di cosa ha
   già stampato.
3. Ogni messaggio mai visto prima viene stampato con
   **`backend/printer.py`** sulla stampante USB collegata a quel Pi, e
   registrato nell'elenco locale solo dopo la stampa riuscita — se la
   stampa fallisce, il messaggio resta "da stampare" e viene ritentato
   automaticamente al ciclo successivo, senza bisogno di nessun
   intervento manuale.

Ogni Pi è completamente indipendente dagli altri: lo stesso messaggio
viene stampato da **tutte** le stampanti collegate, non da una sola.

## Struttura del repository — quale file va dove

Il repository contiene il codice di **tutte** le macchine coinvolte: in
fase di deploy, cartelle diverse finiscono su macchine diverse.

| Cartella nel repo | Va deployata su | Contiene |
|---|---|---|
| [`frontend/`](frontend/) | Hosting condiviso, root del sito | `index.html` (pagina principale: invio + storico), `storico.html` (solo storico, sola lettura) |
| [`hosting/api/`](hosting/api/) | Hosting condiviso, dentro `api/` | Gli endpoint PHP (`message.php`, `history.php`, `like.php`) + `db.php` (funzioni condivise) + `config.php` (credenziali, **non committato**, va creato copiando `config.php.example`) |
| [`hosting/schema.sql`](hosting/schema.sql) | Hosting condiviso, eseguito una volta sul database MySQL | Schema della tabella `messaggi` |
| [`backend/`](backend/) | Ogni Raspberry Pi stampante (uno o più, indipendenti tra loro) | `poller.py` (loop principale), `api_client.py` (chiamate HTTP), `printer.py` (stampa), `.env` (config, **non committato**), `mondo-a-rotoli.service` (systemd) |
| [`bridge/`](bridge/) | Raspberry Pi opzionale, collegato a un MacBook | `fetcher.py` (loop principale), `api_client.py` (chiamate HTTP), `bluetooth_sender.py` (invio via obexftp), `.env` (config, **non committato**), `mondo-a-rotoli-bridge.service` (systemd) |
| [`ledwall/`](ledwall/) | MacBook opzionale, collegato via Bluetooth | `TextWall.py` (loop principale, scrive sul ledwall via UDP), `messaggi_watcher.py` (legge i file ricevuti), `mostrati.jsonl` (stato/archivio, **non committato**, creato al primo avvio) |

Niente, in questo repo, gira sull'hosting E su un Pi contemporaneamente: ogni
cartella ha una sola destinazione. `docs/` non va deployato da nessuna
parte — contiene solo la documentazione di design del progetto.

Le istruzioni di deploy dettagliate, passo per passo, sono nei README di
ciascuna parte:

- [`hosting/README.md`](hosting/README.md) — deploy del backend PHP +
  MySQL e del frontend, endpoint esposti, checklist di test manuale.
- [`backend/README.md`](backend/README.md) — configurazione e avvio del
  poller su ogni Raspberry Pi stampante, esecuzione come servizio
  systemd, come aggiungerne uno nuovo.
- [`frontend/README.md`](frontend/README.md) — nota rapida sul frontend
  (non richiede configurazione per-deploy).
- [`bridge/README.md`](bridge/README.md) — secondo Raspberry Pi
  opzionale: legge lo storico pubblico, salva in locale i messaggi nuovi
  e li manda via Bluetooth a un MacBook. Non necessario per far
  funzionare l'installazione di base.
- [`ledwall/README.md`](ledwall/README.md) — script sul MacBook
  opzionale: mostra su un ledwall via UDP sia il testo digitato a mano
  sia i messaggi ricevuti in automatico dal Pi #2. Non necessario per far
  funzionare l'installazione di base.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: allinea il README principale alla stampa fan-out su piu' stampanti"
```

---

## Verifica finale

- [ ] `cd backend && ./venv/Scripts/python.exe -m pytest -v` — tutti i test passano.
- [ ] `grep -rn "claim.php\|ack.php\|api_key" hosting/ backend/ README.md` (escludendo `docs/superpowers/`) — nessun risultato residuo.
- [ ] Verifica manuale end-to-end reale, quando possibile: un messaggio inviato dal form compare nello storico subito, e viene stampato da **tutte** le stampanti collegate entro una decina di secondi; una stampante spenta al momento dell'invio lo stampa comunque al riavvio, senza sblocco manuale.

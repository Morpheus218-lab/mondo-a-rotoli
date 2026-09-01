# Backend Flask su Raspberry Pi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sostituire il Worker Cloudflare + D1 e il vecchio `poller.py` con un unico processo Flask sul Raspberry Pi che riceve i messaggi, li salva in SQLite locale e li stampa in serie su una stampante USB.

**Architecture:** Flask espone `POST /message` (salva `pending`, mette l'id in coda) e `GET /message/history` (legge i `delivered`). Un thread worker separato consuma la coda e stampa un messaggio alla volta, riusando la logica di generazione immagine/stampa già presente in `poller.py`. Al boot, i messaggi rimasti `pending` da un crash precedente vengono rimessi in coda.

**Tech Stack:** Python 3, Flask, Flask-CORS, Pillow, python-escpos, SQLite (libreria standard `sqlite3`), pytest per i test.

**Spec:** [docs/superpowers/specs/2026-09-01-backend-raspberry-design.md](../specs/2026-09-01-backend-raspberry-design.md)

## Global Constraints

- Limite messaggio: 100 caratteri — oltre, si stampa un avviso invece del testo (validazione lato server).
- Font stampa: Press Start 2P, `FONT_SIZE = 165`.
- Larghezza fisica di stampa: `LARGHEZZA_STAMPA = 576` — valore fisso della testina, non modificare.
- Stampante USB: vendor `0x0416`, product `0x5011`, `in_ep=0x81`, `out_ep=0x01`.
- Schema tabella `messaggi` invariato: `id, text, created_at, status` (`status` è `'pending'` o `'delivered'`).
- Endpoint pubblici esposti dal nuovo backend: solo `POST /message` e `GET /message/history`. `/message/latest` e `/message/ack` non esistono più (erano per il polling esterno, non più necessario).
- CORS abilitato su tutte le rotte.
- Un solo thread worker stampa in serie (la stampante USB non è thread-safe).
- Al boot, i messaggi `pending` residui vengono rimessi in coda prima di aprire il server HTTP.
- Esposizione in rete del Pi: fuori scope, non toccare `frontend/index.html` in questo piano.

---

## File Structure

```
backend/
  requirements.txt        # dipendenze runtime (Flask, Flask-CORS, Pillow, python-escpos)
  requirements-dev.txt     # + pytest, per lo sviluppo/test
  pytest.ini                # pythonpath = . cosi' i test importano i moduli in backend/
  schema.sql                # invariato
  db.py                     # accesso SQLite: insert, mark_delivered, get_pending_ids, get_message, get_history
  printer.py                # generazione immagine + invio alla stampante (da poller.py)
  worker.py                 # coda in memoria + logica del thread di stampa
  app.py                    # Flask app factory (create_app) + entrypoint reale (if __name__ == "__main__")
  fonts/PressStart2P.ttf    # già presente, invariato
  tests/
    test_db.py
    test_printer.py
    test_worker.py
    test_app.py
```

`poller.py` viene rimosso nel Task 5: la sua logica è ora divisa tra `printer.py` (generazione immagine/stampa) e `worker.py` (loop di consumo coda).

---

### Task 1: Setup progetto + `db.py`

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Create: `backend/pytest.ini`
- Create: `backend/schema.sql`
- Create: `backend/db.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces (usate dai task successivi):
  - `db.connect(db_path: str) -> sqlite3.Connection`
  - `db.init_db(conn: sqlite3.Connection) -> None`
  - `db.insert_message(conn, text: str) -> tuple[int, str]` (ritorna `(id, created_at)`)
  - `db.mark_delivered(conn, message_id: int) -> None`
  - `db.get_pending_ids(conn) -> list[int]` (ordine crescente per id)
  - `db.get_message(conn, message_id: int) -> dict | None`
  - `db.get_history(conn, limit: int, offset: int) -> list[dict]` (ordine decrescente per id)

- [ ] **Step 1: Creare `backend/requirements.txt`**

```
Flask
Flask-CORS
Pillow
python-escpos
```

- [ ] **Step 2: Creare `backend/requirements-dev.txt`**

```
-r requirements.txt
pytest
```

- [ ] **Step 3: Creare `backend/pytest.ini`**

```ini
[pytest]
pythonpath = .
testpaths = tests
```

- [ ] **Step 4: Creare virtualenv e installare le dipendenze**

Run:
```bash
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements-dev.txt
```
Expected: installazione senza errori (su Mac `python-escpos` si installa senza bisogno di hardware collegato — serve solo per importare le classi, non per usarle).

- [ ] **Step 5: Creare `backend/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS messaggi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  text TEXT NOT NULL,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
);
```

- [ ] **Step 6: Scrivere i test (falliranno: `db.py` non esiste ancora)**

`backend/tests/test_db.py`:
```python
import db


def _fresh_conn(tmp_path):
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    return conn


def test_insert_message_sets_pending_status(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, created_at = db.insert_message(conn, "ciao")
    row = conn.execute("SELECT * FROM messaggi WHERE id = ?", (message_id,)).fetchone()
    assert row["text"] == "ciao"
    assert row["status"] == "pending"
    assert row["created_at"] == created_at


def test_mark_delivered_updates_status(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    db.mark_delivered(conn, message_id)
    row = conn.execute("SELECT status FROM messaggi WHERE id = ?", (message_id,)).fetchone()
    assert row["status"] == "delivered"


def test_get_pending_ids_returns_only_pending_in_order(tmp_path):
    conn = _fresh_conn(tmp_path)
    id1, _ = db.insert_message(conn, "uno")
    id2, _ = db.insert_message(conn, "due")
    db.mark_delivered(conn, id1)
    id3, _ = db.insert_message(conn, "tre")
    assert db.get_pending_ids(conn) == [id2, id3]


def test_get_message_returns_dict_or_none(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    assert db.get_message(conn, message_id)["text"] == "ciao"
    assert db.get_message(conn, 9999) is None


def test_get_history_returns_delivered_desc_with_pagination(tmp_path):
    conn = _fresh_conn(tmp_path)
    for testo in ["uno", "due", "tre"]:
        message_id, _ = db.insert_message(conn, testo)
        db.mark_delivered(conn, message_id)

    pagina1 = db.get_history(conn, limit=2, offset=0)
    assert [r["text"] for r in pagina1] == ["tre", "due"]

    pagina2 = db.get_history(conn, limit=2, offset=2)
    assert [r["text"] for r in pagina2] == ["uno"]
```

- [ ] **Step 7: Eseguire i test e verificare che falliscano**

Run: `cd backend && pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 8: Implementare `backend/db.py`**

```python
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def connect(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn):
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()


def insert_message(conn, text):
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        "INSERT INTO messaggi (text, created_at, status) VALUES (?, ?, ?)",
        (text, created_at, "pending"),
    )
    conn.commit()
    return cursor.lastrowid, created_at


def mark_delivered(conn, message_id):
    conn.execute("UPDATE messaggi SET status = ? WHERE id = ?", ("delivered", message_id))
    conn.commit()


def get_pending_ids(conn):
    rows = conn.execute(
        "SELECT id FROM messaggi WHERE status = 'pending' ORDER BY id ASC"
    ).fetchall()
    return [row["id"] for row in rows]


def get_message(conn, message_id):
    row = conn.execute("SELECT * FROM messaggi WHERE id = ?", (message_id,)).fetchone()
    return dict(row) if row else None


def get_history(conn, limit, offset):
    rows = conn.execute(
        "SELECT * FROM messaggi WHERE status = 'delivered' ORDER BY id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return [dict(row) for row in rows]
```

Nota: `check_same_thread=False` è necessario perché la stessa connessione verrà usata sia dal thread Flask sia dal thread worker di stampa (Task 3/5). `PRAGMA busy_timeout` evita errori "database is locked" in caso di scritture quasi simultanee dai due thread.

- [ ] **Step 9: Eseguire i test e verificare che passino**

Run: `cd backend && pytest tests/test_db.py -v`
Expected: PASS (5 test)

- [ ] **Step 10: Commit**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/pytest.ini backend/schema.sql backend/db.py backend/tests/test_db.py
git commit -m "feat: aggiungi accesso SQLite locale (db.py)"
```

---

### Task 2: `printer.py`

**Files:**
- Create: `backend/printer.py`
- Test: `backend/tests/test_printer.py`

**Interfaces:**
- Consumes: nessuna interfaccia da task precedenti.
- Produces:
  - `printer.LIMITE_CARATTERI: int` (= 100)
  - `printer.LARGHEZZA_STAMPA: int` (= 576)
  - `printer.crea_immagine_testo(testo: str, font_size=165, larghezza_stampa=576) -> PIL.Image.Image`
  - `printer.stampa_messaggio(stampante, testo: str) -> bool` — `stampante` è un oggetto con metodi `.set(**kwargs)`, `.text(str)`, `.image(PIL.Image.Image)` (duck typing, compatibile con `escpos.printer.Usb`)
  - `printer.get_printer() -> escpos.printer.Usb` (usata solo dall'entrypoint reale in Task 5, importa `escpos` al suo interno)

- [ ] **Step 1: Scrivere i test (falliranno: `printer.py` non esiste ancora)**

`backend/tests/test_printer.py`:
```python
import printer


def test_crea_immagine_testo_ha_larghezza_pari_alla_larghezza_stampa():
    img = printer.crea_immagine_testo("ciao")
    # l'immagine viene ruotata di 90 gradi per la stampa verticale:
    # la larghezza finale corrisponde a LARGHEZZA_STAMPA (altezza prima della rotazione)
    assert img.width == printer.LARGHEZZA_STAMPA


def test_crea_immagine_testo_e_immagine_binaria():
    img = printer.crea_immagine_testo("ciao")
    assert img.mode == "1"


class StampanteFinta:
    def __init__(self):
        self.chiamate = []

    def set(self, **kwargs):
        self.chiamate.append(("set", kwargs))

    def text(self, testo):
        self.chiamate.append(("text", testo))

    def image(self, immagine):
        self.chiamate.append(("image", immagine))


def test_stampa_messaggio_normale_invia_intestazione_e_immagine():
    stampante = StampanteFinta()
    risultato = printer.stampa_messaggio(stampante, "ciao mondo")

    assert risultato is True
    nomi_chiamate = [nome for nome, _ in stampante.chiamate]
    assert nomi_chiamate == ["set", "text", "set", "image"]


def test_stampa_messaggio_troppo_lungo_stampa_avviso_invece_del_testo():
    stampante = StampanteFinta()
    testo_lungo = "a" * (printer.LIMITE_CARATTERI + 1)
    risultato = printer.stampa_messaggio(stampante, testo_lungo)

    assert risultato is True
    nomi_chiamate = [nome for nome, _ in stampante.chiamate]
    assert nomi_chiamate == ["set", "text", "set"]
    testo_stampato = stampante.chiamate[1][1]
    assert "TROPPO LUNGO" in testo_stampato


def test_stampa_messaggio_ritorna_false_se_la_stampante_solleva_eccezione():
    class StampanteRotta:
        def set(self, **kwargs):
            raise RuntimeError("USB scollegata")

    risultato = printer.stampa_messaggio(StampanteRotta(), "ciao")
    assert risultato is False
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `cd backend && pytest tests/test_printer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'printer'`

- [ ] **Step 3: Implementare `backend/printer.py`**

```python
import os

from PIL import Image, ImageDraw, ImageFont

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "PressStart2P.ttf")
FONT_SIZE = 165  # circa 2.6cm di altezza lettere
LARGHEZZA_STAMPA = 576  # larghezza fisica massima della testina, non toccare
LIMITE_CARATTERI = 100


def crea_immagine_testo(testo, font_size=FONT_SIZE, larghezza_stampa=LARGHEZZA_STAMPA):
    font = ImageFont.truetype(FONT_PATH, font_size)
    img_temp = Image.new("1", (1, 1))
    draw_temp = ImageDraw.Draw(img_temp)
    bbox = draw_temp.textbbox((0, 0), testo, font=font)
    larghezza_testo = bbox[2] - bbox[0]
    altezza_testo = bbox[3] - bbox[1]

    margine_lunghezza = 20
    img = Image.new("1", (larghezza_testo + margine_lunghezza * 2, larghezza_stampa), 1)
    draw = ImageDraw.Draw(img)
    y_centrato = (larghezza_stampa - altezza_testo) // 2 - bbox[1]
    draw.text((margine_lunghezza - bbox[0], y_centrato), testo, font=font, fill=0)

    return img.rotate(90, expand=True)


def stampa_messaggio(stampante, testo):
    try:
        if len(testo) > LIMITE_CARATTERI:
            stampante.set(align="center", bold=True, width=1, height=1)
            stampante.text(f"MESSAGGIO TROPPO LUNGO\n(supera {LIMITE_CARATTERI} caratteri)\n")
            stampante.set(align="left", bold=False, width=1, height=1)
            return True

        stampante.set(align="center", bold=True, width=2, height=2)
        stampante.text("PROMPT:\n")
        stampante.set(align="left", bold=False, width=1, height=1)

        immagine = crea_immagine_testo(testo)
        stampante.image(immagine)
        return True
    except Exception:
        return False


def get_printer():
    from escpos.printer import Usb

    return Usb(0x0416, 0x5011, in_ep=0x81, out_ep=0x01)
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `cd backend && pytest tests/test_printer.py -v`
Expected: PASS (5 test)

- [ ] **Step 5: Commit**

```bash
git add backend/printer.py backend/tests/test_printer.py
git commit -m "feat: aggiungi generazione immagine e stampa (printer.py)"
```

---

### Task 3: `worker.py`

**Files:**
- Create: `backend/worker.py`
- Test: `backend/tests/test_worker.py`

**Interfaces:**
- Consumes:
  - `db.get_message(conn, message_id) -> dict | None` (Task 1)
  - `db.mark_delivered(conn, message_id) -> None` (Task 1)
  - `printer.stampa_messaggio(stampante, testo) -> bool` (Task 2)
- Produces:
  - `worker.crea_coda() -> queue.Queue`
  - `worker.process_one(conn, stampante, message_id: int) -> None` — legge il messaggio, lo stampa, aggiorna lo stato
  - `worker.worker_loop(coda: queue.Queue, conn, stampante) -> None` — loop infinito, usato solo dall'entrypoint reale (Task 5) in un thread daemon

- [ ] **Step 1: Scrivere i test (falliranno: `worker.py` non esiste ancora)**

`backend/tests/test_worker.py`:
```python
import queue

import db
import worker


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


def _fresh_conn(tmp_path):
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    return conn


def test_process_one_stampa_e_marca_delivered(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    stampante = StampanteFinta()

    worker.process_one(conn, stampante, message_id)

    assert len(stampante.testi_stampati) == 1
    assert db.get_message(conn, message_id)["status"] == "delivered"


def test_process_one_lascia_pending_se_la_stampa_fallisce(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    stampante = StampanteFinta(fallisce=True)

    worker.process_one(conn, stampante, message_id)

    assert db.get_message(conn, message_id)["status"] == "pending"


def test_process_one_ignora_id_inesistente(tmp_path):
    conn = _fresh_conn(tmp_path)
    stampante = StampanteFinta()

    worker.process_one(conn, stampante, 9999)  # non deve sollevare eccezioni

    assert stampante.testi_stampati == []


def test_process_one_rispetta_ordine_fifo_della_coda(tmp_path):
    conn = _fresh_conn(tmp_path)
    id1, _ = db.insert_message(conn, "uno")
    id2, _ = db.insert_message(conn, "due")

    coda = queue.Queue()
    coda.put(id1)
    coda.put(id2)

    stampante = StampanteFinta()
    worker.process_one(conn, stampante, coda.get())
    worker.process_one(conn, stampante, coda.get())

    assert db.get_message(conn, id1)["status"] == "delivered"
    assert db.get_message(conn, id2)["status"] == "delivered"
```

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `cd backend && pytest tests/test_worker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'worker'`

- [ ] **Step 3: Implementare `backend/worker.py`**

```python
import logging
import queue

import db
import printer

logger = logging.getLogger(__name__)


def crea_coda():
    return queue.Queue()


def process_one(conn, stampante, message_id):
    messaggio = db.get_message(conn, message_id)
    if messaggio is None:
        return

    riuscito = printer.stampa_messaggio(stampante, messaggio["text"])
    if riuscito:
        db.mark_delivered(conn, message_id)
    else:
        logger.error("Stampa fallita per il messaggio %s, resta pending", message_id)


def worker_loop(coda, conn, stampante):
    while True:
        message_id = coda.get()
        try:
            process_one(conn, stampante, message_id)
        except Exception:
            logger.exception("Errore inatteso processando il messaggio %s", message_id)
        finally:
            coda.task_done()
```

Nota: `worker_loop` è un loop infinito pensato per girare in un thread daemon (viene collegato nel Task 5) — non è testato direttamente qui, ma tramite `process_one`, che contiene tutta la logica non banale.

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `cd backend && pytest tests/test_worker.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Commit**

```bash
git add backend/worker.py backend/tests/test_worker.py
git commit -m "feat: aggiungi coda e worker di stampa seriale (worker.py)"
```

---

### Task 4: `app.py` — rotte Flask

**Files:**
- Create: `backend/app.py`
- Test: `backend/tests/test_app.py`

**Interfaces:**
- Consumes:
  - `db.connect`, `db.init_db`, `db.insert_message`, `db.mark_delivered`, `db.get_message`, `db.get_history` (Task 1)
  - I test usano `queue.Queue()` direttamente (libreria standard) per simulare la coda — non serve importare `worker` in `test_app.py`, dato che `create_app` accetta qualunque oggetto con un metodo `.put()`.
- Produces:
  - `app.create_app(conn, coda: queue.Queue) -> flask.Flask`

- [ ] **Step 1: Scrivere i test (falliranno: `app.py` non esiste ancora)**

`backend/tests/test_app.py`:
```python
import queue

import pytest

import app as app_module
import db


@pytest.fixture
def client(tmp_path):
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    coda = queue.Queue()
    flask_app = app_module.create_app(conn, coda)
    flask_app.config["TESTING"] = True
    return flask_app.test_client(), conn, coda


def test_post_message_salva_pending_e_accoda(client):
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": "ciao mondo"})

    assert risposta.status_code == 202
    corpo = risposta.get_json()
    assert corpo["ok"] is True
    assert isinstance(corpo["id"], int)

    riga = db.get_message(conn, corpo["id"])
    assert riga["text"] == "ciao mondo"
    assert riga["status"] == "pending"
    assert coda.get_nowait() == corpo["id"]


def test_post_message_senza_testo_ritorna_400(client):
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": "   "})

    assert risposta.status_code == 400
    assert coda.empty()


def test_get_history_ritorna_solo_delivered(client):
    test_client, conn, coda = client
    id1, _ = db.insert_message(conn, "uno")
    db.mark_delivered(conn, id1)
    db.insert_message(conn, "due")  # resta pending, non deve comparire

    risposta = test_client.get("/message/history")

    assert risposta.status_code == 200
    messaggi = risposta.get_json()["messaggi"]
    assert len(messaggi) == 1
    assert messaggi[0]["text"] == "uno"


def test_get_history_rispetta_limit_e_offset(client):
    test_client, conn, coda = client
    for testo in ["uno", "due", "tre"]:
        message_id, _ = db.insert_message(conn, testo)
        db.mark_delivered(conn, message_id)

    risposta = test_client.get("/message/history?limit=1&offset=1")

    messaggi = risposta.get_json()["messaggi"]
    assert [m["text"] for m in messaggi] == ["due"]
```

Nota: `db.mark_delivered` va importato in `test_app.py` insieme a `db.insert_message` (entrambi già esposti da `db.py`, Task 1) — aggiungere `from db import mark_delivered` non serve, si usa `db.mark_delivered` dato che il modulo è importato come `db`.

- [ ] **Step 2: Eseguire i test e verificare che falliscano**

Run: `cd backend && pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Implementare `backend/app.py` (solo la app factory, senza entrypoint reale)**

```python
from flask import Flask, jsonify, request
from flask_cors import CORS

import db

DEFAULT_LIMIT = 10


def create_app(conn, coda):
    app = Flask(__name__)
    CORS(app)

    @app.post("/message")
    def message():
        corpo = request.get_json(silent=True) or {}
        testo = (corpo.get("text") or "").strip()

        if not testo:
            return jsonify({"error": 'Il campo "text" è obbligatorio'}), 400

        message_id, created_at = db.insert_message(conn, testo)
        coda.put(message_id)

        return jsonify({"ok": True, "id": message_id, "createdAt": created_at}), 202

    @app.get("/message/history")
    def history():
        limit = request.args.get("limit", default=DEFAULT_LIMIT, type=int)
        offset = request.args.get("offset", default=0, type=int)
        messaggi = db.get_history(conn, limit, offset)
        return jsonify({"messaggi": messaggi})

    return app
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `cd backend && pytest tests/test_app.py -v`
Expected: PASS (4 test)

- [ ] **Step 5: Eseguire l'intera suite di test**

Run: `cd backend && pytest -v`
Expected: PASS (18 test in totale: 5 db + 5 printer + 4 worker + 4 app)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_app.py
git commit -m "feat: aggiungi rotte Flask POST /message e GET /message/history"
```

---

### Task 5: Entrypoint reale, rimozione `poller.py`, README

**Files:**
- Modify: `backend/app.py` (aggiungere l'entrypoint `if __name__ == "__main__":`)
- Delete: `backend/poller.py`
- Modify: `backend/README.md`

**Interfaces:**
- Consumes:
  - `db.connect`, `db.init_db`, `db.get_pending_ids` (Task 1)
  - `worker.crea_coda`, `worker.worker_loop` (Task 3)
  - `printer.get_printer` (Task 2)
  - `app.create_app` (Task 4)

- [ ] **Step 1: Aggiungere l'entrypoint reale in fondo a `backend/app.py`**

Aggiungere questi import in cima al file (sotto quelli già presenti):
```python
import os
import threading

import printer as printer_module
import worker
```

Aggiungere in fondo al file:
```python
DB_PATH = os.path.join(os.path.dirname(__file__), "installazione.db")


def _recupera_pending(conn, coda):
    for message_id in db.get_pending_ids(conn):
        coda.put(message_id)


if __name__ == "__main__":
    conn = db.connect(DB_PATH)
    db.init_db(conn)

    coda = worker.crea_coda()
    _recupera_pending(conn, coda)

    stampante = printer_module.get_printer()
    thread_stampa = threading.Thread(
        target=worker.worker_loop, args=(coda, conn, stampante), daemon=True
    )
    thread_stampa.start()

    app = create_app(conn, coda)
    app.run(host="0.0.0.0", port=5000)
```

- [ ] **Step 2: Verificare che il modulo si importi senza errori (senza hardware)**

Run: `cd backend && python3 -c "import app"`
Expected: nessun errore — il blocco `if __name__ == "__main__":` non viene eseguito durante un `import`, quindi non serve una stampante reale collegata per questo controllo.

- [ ] **Step 3: Rimuovere il vecchio `poller.py`**

Run: `git rm backend/poller.py`
Expected: la logica è ora divisa tra `printer.py` (Task 2) e `worker.py` (Task 3).

- [ ] **Step 4: Aggiornare `backend/README.md`**

```markdown
# backend

Server Flask che gira sul Raspberry Pi Zero: riceve i messaggi dal
frontend, li salva in SQLite locale (`installazione.db`, creato al primo
avvio) e li stampa in serie sulla stampante USB collegata.

Sostituisce il precedente Worker Cloudflare + `poller.py`. Vedi la spec
completa in
`../docs/superpowers/specs/2026-09-01-backend-raspberry-design.md`.

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
python3 app.py
```

Il server ascolta su `0.0.0.0:5000`. L'esposizione verso internet (dominio,
port forwarding, ecc.) è decisa separatamente — non ancora configurata.
```

- [ ] **Step 5: Eseguire di nuovo l'intera suite di test**

Run: `cd backend && pytest -v`
Expected: PASS (18 test, invariati rispetto al Task 4 — questo task non aggiunge logica testabile)

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/README.md
git commit -m "feat: aggiungi entrypoint reale e rimuovi il vecchio poller.py"
```

---

### Task 6: Verifica manuale end-to-end sul Raspberry Pi

Questo task non produce codice: verifica che il nuovo backend funzioni con l'hardware reale (stampante USB), cosa che non è testabile in automatico da questa macchina di sviluppo. Segue la sezione "Testing" della spec.

**Files:** nessuno (solo comandi da eseguire, sul Mac e sul Pi).

- [ ] **Step 1: Copiare la cartella `backend/` aggiornata sul Pi, escludendo `venv`**

Run (dal Mac):
```bash
rsync -avz --exclude venv --exclude __pycache__ --exclude '*.db' \
  /Users/luigimazza/Documents/Projects/mondo-a-rotoli/backend/ \
  pi@txtinstallazione.local:~/txtinstallazione/
```
Expected: file `.py`, `requirements*.txt`, `schema.sql`, `pytest.ini`, `fonts/` copiati; niente `venv` sovrascritto.

- [ ] **Step 2: Sul Pi, reinstallare le dipendenze runtime**

Run (via SSH sul Pi):
```bash
cd ~/txtinstallazione && source venv/bin/activate && pip install -r requirements.txt
```
Expected: installazione senza errori (qui `python-escpos` deve poter accedere all'hardware USB — verificare che l'utente `pi` abbia i permessi sulla porta USB, come già configurato per il vecchio `poller.py`).

- [ ] **Step 3: Avviare il server sul Pi**

Run (via SSH sul Pi, stampante USB collegata):
```bash
cd ~/txtinstallazione && source venv/bin/activate && python3 app.py
```
Expected: il processo resta in ascolto senza errori, nessuna eccezione all'avvio (creazione DB + recupero pending, anche se vuoto la prima volta).

- [ ] **Step 4: Inviare un messaggio normale e verificare la stampa fisica**

Run (da un'altra macchina sulla stessa rete):
```bash
curl -X POST http://txtinstallazione.local:5000/message \
  -H "Content-Type: application/json" \
  -d '{"text": "test end-to-end"}'
```
Expected: risposta `202` con `{"ok": true, "id": ..., "createdAt": ...}`; la stampante stampa fisicamente "PROMPT:" seguito dal testo.

- [ ] **Step 5: Inviare un messaggio oltre i 100 caratteri e verificare l'avviso**

Run:
```bash
curl -X POST http://txtinstallazione.local:5000/message \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$(python3 -c 'print("a"*150)')\"}"
```
Expected: risposta `202`; la stampante stampa l'avviso "MESSAGGIO TROPPO LUNGO" invece del testo.

- [ ] **Step 6: Verificare lo storico**

Run:
```bash
curl http://txtinstallazione.local:5000/message/history
```
Expected: risposta `200` con entrambi i messaggi del Step 4 e 5, `status` implicito `delivered` (non compare nel JSON ma erano stampati correttamente), più recente per primo.

- [ ] **Step 7: Verificare il crash recovery**

Con il server ancora in esecuzione, da un'altra sessione SSH sul Pi:
```bash
cd ~/txtinstallazione && source venv/bin/activate && python3 -c "
import db
conn = db.connect('installazione.db')
db.insert_message(conn, 'messaggio pending simulato')
"
```
Poi fermare il server (`Ctrl+C`) e riavviarlo (`python3 app.py`).
Expected: al riavvio, il messaggio "messaggio pending simulato" viene stampato automaticamente (recuperato dalla coda `pending`), senza bisogno di rifare la `POST`.

- [ ] **Step 8: Annotare l'esito**

Se tutti gli step precedenti sono passati, il backend è pronto. Non è richiesto nessun commit per questo task (nessun file modificato) — se durante la verifica emergono problemi, tornare ai task precedenti per correggerli, aggiungendo un test che riproduce il problema prima di correggerlo.

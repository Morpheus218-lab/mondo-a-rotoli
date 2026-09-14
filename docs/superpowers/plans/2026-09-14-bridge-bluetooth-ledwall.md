# Invio automatico Pi#2 -> Mac via Bluetooth verso il ledwall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Il Pi #2 manda automaticamente `messaggi.jsonl` al MacBook via Bluetooth ogni volta che trova messaggi nuovi; `TextWall.py` sul Mac scopre i file ricevuti, estrae i messaggi mai visti, li accoda e li mostra sul ledwall uno alla volta, cedendo sempre priorità all'input manuale da terminale.

**Architecture:** `bridge/bluetooth_sender.py` (nuovo) incapsula la chiamata a `obexftp` via `subprocess`; `bridge/fetcher.py` lo richiama dopo ogni ciclo che scrive messaggi nuovi. Sul Mac, `walltext/messaggi_watcher.py` (nuovo) offre funzioni pure per scoprire i file ricevuti, estrarne i messaggi mai visti (stesso algoritmo a insieme-di-id già usato in `fetcher.py`, contro un archivio permanente `mostrati.jsonl`) e decidere quando avanzare la coda automatica; `TextWall.py` le richiama dal suo loop principale.

**Tech Stack:** Python 3 (Pi: stdlib `subprocess`; Mac: stdlib `glob`/`json`/`collections.deque`), `obexftp` (pacchetto di sistema sul Pi), `pytest` per i test.

**Spec:** [docs/superpowers/specs/2026-09-14-bridge-bluetooth-ledwall-design.md](../specs/2026-09-14-bridge-bluetooth-ledwall-design.md)

## Global Constraints

- Il successo di un invio Bluetooth si legge cercando `"Sending"` e `"/done"` nell'output di `obexftp`, MAI dal solo codice di uscita del processo (può essere diverso da zero per un "Disconnecting failed" innocuo).
- Il file mandato dal Pi è cumulativo: ogni invio ripropone anche i messaggi già mandati prima. La dedup, su entrambe le macchine, è sempre per **insieme di id già visti**, mai per "ultimo id" (un messaggio può arrivare con id più basso di uno già visto, es. se era rimasto bloccato in `printing`).
- Righe non leggibili come JSON in un file `.jsonl` vengono ignorate con un warning, senza bloccare la lettura delle righe successive.
- Il Mac non sovrascrive mai i file duplicati Bluetooth (li rinomina `messaggi #1.jsonl`, ecc.): vanno cancellati esplicitamente dopo la lettura.
- L'input manuale da terminale in `TextWall.py` ha sempre precedenza immediata; l'automatico riprende `IDLE_TIMEOUT_MANUALE` (default 15s) secondi dopo l'ultima interazione da tastiera, qualunque essa sia stata.
- `DURATA_MESSAGGIO_AUTO` default 8s, `INTERVALLO_CONTROLLO_CARTELLA` default 2s.
- L'invio Bluetooth sul Pi è opzionale: se `MACBOOK_BT_ADDRESS`/`BT_OBEX_CHANNEL` non sono configurate, il bridge continua a funzionare come oggi (nessun invio, nessun errore).
- La cartella `walltext` (progetto Mac, path locale `C:\Users\alph2\OneDrive\WINZOZ_S\Documents\Project\walltext`, sul Mac `~/Desktop/WallText`) non è un repository git — è fuori scope in questa feature. I task che la toccano terminano con "salva il file", non con un commit.

---

## Task 1: `bridge/bluetooth_sender.py` — invio via OBEX Object Push

**Files:**
- Create: `bridge/bluetooth_sender.py`
- Test: `bridge/tests/test_bluetooth_sender.py`

**Interfaces:**
- Produces: `invia_file(path: str, indirizzo_mac: str, canale) -> bool`

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `bridge/tests/test_bluetooth_sender.py`:

```python
# bridge/tests/test_bluetooth_sender.py
import bluetooth_sender


class ProcessoFinto:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_invia_file_ritorna_true_se_lo_stdout_conferma_l_invio(monkeypatch):
    stdout = (
        'Connecting..\\done\n'
        'Sending "messaggi.jsonl".../done\n'
        'Disconnecting..-failed: disconnect\n'
    )
    monkeypatch.setattr(
        bluetooth_sender.subprocess,
        "run",
        lambda *a, **k: ProcessoFinto(stdout=stdout, returncode=1),
    )

    assert bluetooth_sender.invia_file("messaggi.jsonl", "A4:CF:99:61:92:F8", 10) is True


def test_invia_file_ritorna_false_se_manca_la_conferma_di_invio(monkeypatch):
    monkeypatch.setattr(
        bluetooth_sender.subprocess,
        "run",
        lambda *a, **k: ProcessoFinto(stdout="", stderr="connect failed", returncode=1),
    )

    assert bluetooth_sender.invia_file("messaggi.jsonl", "A4:CF:99:61:92:F8", 10) is False
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd bridge && ./venv/Scripts/python.exe -m pytest tests/test_bluetooth_sender.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'bluetooth_sender'`

- [ ] **Step 3: Implementazione minima**

Crea `bridge/bluetooth_sender.py`:

```python
# bridge/bluetooth_sender.py
import logging
import subprocess

logger = logging.getLogger(__name__)


def invia_file(path, indirizzo_mac, canale):
    """Invia path al Mac via OBEX Object Push (obexftp). Ritorna True se
    l'output del comando conferma l'invio (contiene "Sending" e "/done"),
    anche se il comando termina con un errore di disconnessione: e' un
    dettaglio noto di obexftp, il Mac chiude la connessione OBEX subito
    dopo il trasferimento, prima della disconnessione esplicita - il file
    arriva comunque."""
    risultato = subprocess.run(
        ["obexftp", "-b", indirizzo_mac, "-B", str(canale), "-p", str(path)],
        capture_output=True,
        text=True,
    )
    output = (risultato.stdout or "") + (risultato.stderr or "")
    return "Sending" in output and "/done" in output
```

- [ ] **Step 4: Verifica che passi**

Run: `cd bridge && ./venv/Scripts/python.exe -m pytest tests/test_bluetooth_sender.py -v`
Expected: PASS (2 test)

- [ ] **Step 5: Aggiungi il test sugli argomenti passati al comando**

Aggiungi a `bridge/tests/test_bluetooth_sender.py`:

```python
def test_invia_file_passa_indirizzo_canale_e_percorso_al_comando(monkeypatch):
    chiamate = []

    def run_finto(comando, **kwargs):
        chiamate.append(comando)
        return ProcessoFinto(stdout='Sending "x".../done')

    monkeypatch.setattr(bluetooth_sender.subprocess, "run", run_finto)

    bluetooth_sender.invia_file("messaggi.jsonl", "A4:CF:99:61:92:F8", 10)

    assert chiamate[0] == [
        "obexftp", "-b", "A4:CF:99:61:92:F8", "-B", "10", "-p", "messaggi.jsonl",
    ]
```

- [ ] **Step 6: Verifica che passi**

Run: `cd bridge && ./venv/Scripts/python.exe -m pytest tests/test_bluetooth_sender.py -v`
Expected: PASS (3 test)

- [ ] **Step 7: Commit**

```bash
git add bridge/bluetooth_sender.py bridge/tests/test_bluetooth_sender.py
git commit -m "feat: aggiungi bridge/bluetooth_sender.py per l'invio via obexftp"
```

---

## Task 2: Integra l'invio Bluetooth in `bridge/fetcher.py`

**Files:**
- Modify: `bridge/fetcher.py`
- Modify: `bridge/tests/test_fetcher.py`
- Modify: `bridge/README.md`

**Interfaces:**
- Consumes: `bluetooth_sender.invia_file(path, indirizzo_mac, canale) -> bool` (Task 1)
- Produces: `process_one_ciclo(base_url, output_path, indirizzo_mac=None, canale=None)`, `fetcher_loop(base_url, output_path, indirizzo_mac=None, canale=None)`

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `bridge/tests/test_fetcher.py` (in cima al file c'è già `import fetcher`; aggiungi anche `import json` se non presente — è già importato dal test esistente):

```python
def test_invia_via_bluetooth_quando_configurato_e_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 1, "text": "ciao"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    chiamate = []
    monkeypatch.setattr(
        fetcher.bluetooth_sender,
        "invia_file",
        lambda path, mac, canale: chiamate.append((path, mac, canale)) or True,
    )

    fetcher.process_one_ciclo(
        "http://esempio", str(output_path), indirizzo_mac="A4:CF:99:61:92:F8", canale=10
    )

    assert chiamate == [(str(output_path), "A4:CF:99:61:92:F8", 10)]


def test_non_invia_via_bluetooth_se_non_configurato(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 1, "text": "ciao"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def invia_file_non_atteso(*a, **k):
        raise AssertionError("invia_file non doveva essere chiamato")

    monkeypatch.setattr(fetcher.bluetooth_sender, "invia_file", invia_file_non_atteso)

    fetcher.process_one_ciclo("http://esempio", str(output_path))  # nessun mac/canale


def test_non_invia_via_bluetooth_se_non_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    output_path.write_text(json.dumps({"id": 1, "text": "a"}) + "\n", encoding="utf-8")
    storico = [{"id": 1, "text": "a"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def invia_file_non_atteso(*a, **k):
        raise AssertionError("invia_file non doveva essere chiamato")

    monkeypatch.setattr(fetcher.bluetooth_sender, "invia_file", invia_file_non_atteso)

    fetcher.process_one_ciclo(
        "http://esempio", str(output_path), indirizzo_mac="A4:CF:99:61:92:F8", canale=10
    )


def test_gestisce_errore_durante_invio_bluetooth_senza_sollevare(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 1, "text": "ciao"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def invia_file_rotto(*a, **k):
        raise RuntimeError("bluetooth non disponibile")

    monkeypatch.setattr(fetcher.bluetooth_sender, "invia_file", invia_file_rotto)

    fetcher.process_one_ciclo(  # non deve sollevare
        "http://esempio", str(output_path), indirizzo_mac="A4:CF:99:61:92:F8", canale=10
    )

    contenuto = output_path.read_text(encoding="utf-8")
    assert json.dumps({"id": 1, "text": "ciao"}, ensure_ascii=False) in contenuto
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd bridge && ./venv/Scripts/python.exe -m pytest tests/test_fetcher.py -v`
Expected: FAIL — `AttributeError: module 'fetcher' has no attribute 'bluetooth_sender'` (o `TypeError` su `indirizzo_mac`/`canale` inattesi), a seconda del test.

- [ ] **Step 3: Implementazione minima**

In `bridge/fetcher.py`, aggiungi l'import (dopo `import api_client`):

```python
import bluetooth_sender
```

Sostituisci la fine di `process_one_ciclo` (dal blocco `if not nuovi:` in poi) con:

```python
    if not nuovi:
        return

    with open(output_path, "a", encoding="utf-8") as f:
        for messaggio in nuovi:
            f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")

    if indirizzo_mac and canale:
        try:
            inviato = bluetooth_sender.invia_file(str(output_path), indirizzo_mac, canale)
            if not inviato:
                logger.error("Invio Bluetooth del file al Mac non confermato dall'output di obexftp")
        except Exception:
            logger.exception("Errore durante l'invio Bluetooth del file al Mac")
```

E aggiorna la firma della funzione (riga con `def process_one_ciclo`):

```python
def process_one_ciclo(base_url, output_path, indirizzo_mac=None, canale=None):
```

Aggiorna anche `fetcher_loop` e il blocco `__main__`:

```python
def fetcher_loop(base_url, output_path, indirizzo_mac=None, canale=None):
    while True:
        try:
            process_one_ciclo(base_url, output_path, indirizzo_mac, canale)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di fetch")
        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    base_url = os.environ["API_BASE_URL"]
    output_path = os.environ.get("OUTPUT_FILE", "messaggi.jsonl")
    indirizzo_mac = os.environ.get("MACBOOK_BT_ADDRESS")
    canale = os.environ.get("BT_OBEX_CHANNEL")

    if not indirizzo_mac or not canale:
        logger.info("MACBOOK_BT_ADDRESS/BT_OBEX_CHANNEL non configurate: invio Bluetooth disattivato")

    fetcher_loop(base_url, output_path, indirizzo_mac, canale)
```

- [ ] **Step 4: Verifica che passino**

Run: `cd bridge && ./venv/Scripts/python.exe -m pytest -v`
Expected: PASS (tutti i test di `bridge/`, inclusi quelli invariati di Task 1)

- [ ] **Step 5: Documenta le nuove variabili d'ambiente**

In `bridge/README.md`, nella sezione "## Configurazione", sostituisci il blocco d'esempio con:

```
API_BASE_URL=https://TUO_DOMINIO/api
OUTPUT_FILE=/home/pi/mondo-a-rotoli/bridge/messaggi.jsonl
MACBOOK_BT_ADDRESS=A4:CF:99:61:92:F8
BT_OBEX_CHANNEL=10
```

e subito sotto il paragrafo su `OUTPUT_FILE` aggiungi:

```
`MACBOOK_BT_ADDRESS` e `BT_OBEX_CHANNEL` sono opzionali: se assenti, il
bridge funziona come prima, senza inviare nulla via Bluetooth. Il Mac deve
essere già accoppiato (`bluetoothctl pair`/`trust`) e avere la
Condivisione Bluetooth attiva con "Accetta e salva" verso la cartella
desiderata. Il canale OBEX Object Push si scopre con:

```bash
sudo apt install -y obexftp
sdptool browse MACBOOK_BT_ADDRESS
```

cercando la voce "OBEX Object Push" e il suo `Channel` — può cambiare se
il pairing viene rifatto da zero, in quel caso va riscoperto.
```

- [ ] **Step 6: Commit**

```bash
git add bridge/fetcher.py bridge/tests/test_fetcher.py bridge/README.md
git commit -m "feat: bridge invia messaggi.jsonl al Mac via Bluetooth dopo ogni ciclo con messaggi nuovi"
```

---

## Task 3: `walltext/messaggi_watcher.py` — scoperta file e dedup (funzioni pure)

**Files:**
- Create: `walltext/messaggi_watcher.py`
- Create: `walltext/tests/test_messaggi_watcher.py`
- Create: `walltext/pytest.ini`
- Create: `walltext/requirements-dev.txt`

**Interfaces:**
- Produces: `trova_file_messaggi(cartella) -> list[str]`, `carica_id_mostrati(file_stato) -> set`, `estrai_nuovi(path, id_gia_mostrati) -> list[dict]`

- [ ] **Step 1: Crea l'infrastruttura di test (prima volta per questo progetto)**

Crea `walltext/pytest.ini`:

```ini
[pytest]
pythonpath = .
testpaths = tests
```

Crea `walltext/requirements-dev.txt`:

```
pytest
```

- [ ] **Step 2: Scrivi i test che falliscono**

Crea `walltext/tests/test_messaggi_watcher.py`:

```python
# walltext/tests/test_messaggi_watcher.py
import json
import os
import time

import messaggi_watcher


def scrivi_jsonl(path, messaggi):
    path.write_text(
        "\n".join(json.dumps(m, ensure_ascii=False) for m in messaggi) + "\n", encoding="utf-8"
    )


def test_trova_file_messaggi_ordina_per_data_di_modifica(tmp_path):
    vecchio = tmp_path / "messaggi.jsonl"
    nuovo = tmp_path / "messaggi #1.jsonl"
    vecchio.write_text("{}", encoding="utf-8")
    time.sleep(0.01)
    nuovo.write_text("{}", encoding="utf-8")
    (tmp_path / "altro.txt").write_text("non e' un messaggio", encoding="utf-8")

    trovati = messaggi_watcher.trova_file_messaggi(str(tmp_path))

    assert [os.path.basename(p) for p in trovati] == ["messaggi.jsonl", "messaggi #1.jsonl"]


def test_carica_id_mostrati_ritorna_insieme_vuoto_se_il_file_non_esiste(tmp_path):
    assert messaggi_watcher.carica_id_mostrati(str(tmp_path / "mostrati.jsonl")) == set()


def test_carica_id_mostrati_legge_gli_id_gia_presenti(tmp_path):
    file_stato = tmp_path / "mostrati.jsonl"
    scrivi_jsonl(file_stato, [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}])

    assert messaggi_watcher.carica_id_mostrati(str(file_stato)) == {1, 2}


def test_carica_id_mostrati_ignora_una_riga_corrotta(tmp_path):
    file_stato = tmp_path / "mostrati.jsonl"
    file_stato.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\nnon e' json valido\n", encoding="utf-8"
    )

    assert messaggi_watcher.carica_id_mostrati(str(file_stato)) == {1}


def test_estrai_nuovi_ritorna_solo_i_messaggi_non_gia_mostrati(tmp_path):
    path = tmp_path / "messaggi.jsonl"
    scrivi_jsonl(path, [{"id": 3, "text": "c"}, {"id": 2, "text": "b"}, {"id": 1, "text": "a"}])

    nuovi = messaggi_watcher.estrai_nuovi(str(path), {1})

    assert [m["id"] for m in nuovi] == [2, 3]  # dal piu' vecchio al piu' nuovo
```

- [ ] **Step 3: Verifica che falliscano**

Run: `cd walltext && python3 -m venv venv && ./venv/Scripts/python.exe -m pip install -r requirements-dev.txt && ./venv/Scripts/python.exe -m pytest -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'messaggi_watcher'`

- [ ] **Step 4: Implementazione minima**

Crea `walltext/messaggi_watcher.py`:

```python
# walltext/messaggi_watcher.py
import glob
import json
import logging
import os

logger = logging.getLogger(__name__)


def trova_file_messaggi(cartella):
    """Ritorna i path dei file messaggi*.jsonl in cartella, ordinati dal
    piu' vecchio al piu' nuovo (data di modifica)."""
    percorsi = glob.glob(os.path.join(cartella, "messaggi*.jsonl"))
    return sorted(percorsi, key=os.path.getmtime)


def carica_id_mostrati(file_stato):
    """Ritorna l'insieme degli id gia' presenti in file_stato. Righe non
    leggibili come JSON vengono ignorate con un warning, senza bloccare
    la lettura delle righe successive."""
    if not os.path.exists(file_stato):
        return set()

    id_visti = set()
    with open(file_stato, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                id_visti.add(json.loads(riga)["id"])
            except (json.JSONDecodeError, KeyError):
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, file_stato)

    return id_visti


def estrai_nuovi(path, id_gia_mostrati):
    """Ritorna i messaggi di path con id non in id_gia_mostrati, dal piu'
    vecchio al piu' nuovo. Righe non leggibili vengono ignorate con un
    warning."""
    nuovi = []
    with open(path, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                messaggio = json.loads(riga)
            except json.JSONDecodeError:
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, path)
                continue
            if messaggio.get("id") not in id_gia_mostrati:
                nuovi.append(messaggio)

    nuovi.sort(key=lambda m: m["id"])
    return nuovi
```

- [ ] **Step 5: Verifica che passino**

Run: `cd walltext && ./venv/Scripts/python.exe -m pytest -v`
Expected: PASS (5 test)

- [ ] **Step 6: Salva**

Nessun commit (cartella `walltext` non versionata, vedi Global Constraints) — verifica solo che i file siano salvati e i test passino.

---

## Task 4: `walltext/messaggi_watcher.py` — `elabora_cartella` (orchestrazione + pulizia)

**Files:**
- Modify: `walltext/messaggi_watcher.py`
- Modify: `walltext/tests/test_messaggi_watcher.py`

**Interfaces:**
- Consumes: `trova_file_messaggi`, `carica_id_mostrati`, `estrai_nuovi` (Task 3)
- Produces: `elabora_cartella(cartella, file_stato) -> list[dict]`

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `walltext/tests/test_messaggi_watcher.py`:

```python
def test_elabora_cartella_estrae_messaggi_di_piu_file_e_aggiorna_lo_stato(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"
    scrivi_jsonl(cartella / "messaggi.jsonl", [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}])
    time.sleep(0.01)
    scrivi_jsonl(cartella / "messaggi #1.jsonl", [{"id": 2, "text": "b"}, {"id": 3, "text": "c"}])

    nuovi = messaggi_watcher.elabora_cartella(str(cartella), str(file_stato))

    assert [m["id"] for m in nuovi] == [1, 2, 3]
    assert messaggi_watcher.carica_id_mostrati(str(file_stato)) == {1, 2, 3}


def test_elabora_cartella_cancella_i_file_sorgente(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"
    percorso = cartella / "messaggi.jsonl"
    scrivi_jsonl(percorso, [{"id": 1, "text": "a"}])

    messaggi_watcher.elabora_cartella(str(cartella), str(file_stato))

    assert not percorso.exists()


def test_elabora_cartella_cancella_anche_se_non_ci_sono_messaggi_nuovi(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"
    scrivi_jsonl(file_stato, [{"id": 1, "text": "a"}])
    percorso = cartella / "messaggi.jsonl"
    scrivi_jsonl(percorso, [{"id": 1, "text": "a"}])  # gia' tutto visto

    nuovi = messaggi_watcher.elabora_cartella(str(cartella), str(file_stato))

    assert nuovi == []
    assert not percorso.exists()


def test_elabora_cartella_su_cartella_vuota_ritorna_lista_vuota(tmp_path):
    cartella = tmp_path / "ricevuti"
    cartella.mkdir()
    file_stato = tmp_path / "mostrati.jsonl"

    assert messaggi_watcher.elabora_cartella(str(cartella), str(file_stato)) == []
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd walltext && ./venv/Scripts/python.exe -m pytest tests/test_messaggi_watcher.py -v`
Expected: FAIL con `AttributeError: module 'messaggi_watcher' has no attribute 'elabora_cartella'`

- [ ] **Step 3: Implementazione minima**

Aggiungi in fondo a `walltext/messaggi_watcher.py`:

```python
def elabora_cartella(cartella, file_stato):
    """Elabora tutti i file messaggi*.jsonl trovati in cartella: estrae i
    messaggi mai visti (rispetto a file_stato), li appende a file_stato e
    cancella il file sorgente (anche se non conteneva nulla di nuovo).
    Ritorna la lista di tutti i messaggi nuovi trovati, in ordine (dal
    file piu' vecchio al piu' nuovo, e dentro ciascun file dal messaggio
    piu' vecchio al piu' nuovo)."""
    id_gia_mostrati = carica_id_mostrati(file_stato)
    tutti_nuovi = []

    for path in trova_file_messaggi(cartella):
        nuovi = estrai_nuovi(path, id_gia_mostrati)
        if nuovi:
            with open(file_stato, "a", encoding="utf-8") as f:
                for messaggio in nuovi:
                    f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")
            for messaggio in nuovi:
                id_gia_mostrati.add(messaggio["id"])
            tutti_nuovi.extend(nuovi)
        os.remove(path)

    return tutti_nuovi
```

- [ ] **Step 4: Verifica che passino**

Run: `cd walltext && ./venv/Scripts/python.exe -m pytest -v`
Expected: PASS (9 test)

- [ ] **Step 5: Salva**

Nessun commit (vedi Global Constraints).

---

## Task 5: `walltext/messaggi_watcher.py` — decisione coda automatica vs input manuale

**Files:**
- Modify: `walltext/messaggi_watcher.py`
- Modify: `walltext/tests/test_messaggi_watcher.py`

**Interfaces:**
- Produces: `prossimo_testo_automatico(coda_auto, ultimo_input_manuale, inizio_messaggio_corrente, ora, idle_timeout_manuale, durata_messaggio_auto) -> dict | None`

- [ ] **Step 1: Scrivi i test che falliscono**

Aggiungi a `walltext/tests/test_messaggi_watcher.py` (in cima al file aggiungi `from collections import deque`):

```python
def test_prossimo_testo_automatico_aspetta_il_timeout_dall_ultimo_input_manuale():
    coda = deque([{"id": 1, "text": "a"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=100.0, inizio_messaggio_corrente=None,
        ora=105.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato is None
    assert len(coda) == 1  # non consumato


def test_prossimo_testo_automatico_parte_subito_se_non_c_e_nulla_in_mostra():
    coda = deque([{"id": 1, "text": "a"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=None,
        ora=1000.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato == {"id": 1, "text": "a"}
    assert len(coda) == 0  # consumato


def test_prossimo_testo_automatico_aspetta_la_durata_del_messaggio_corrente():
    coda = deque([{"id": 2, "text": "b"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=1000.0,
        ora=1003.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato is None
    assert len(coda) == 1


def test_prossimo_testo_automatico_avanza_dopo_la_durata_del_messaggio_corrente():
    coda = deque([{"id": 2, "text": "b"}])

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=1000.0,
        ora=1008.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato == {"id": 2, "text": "b"}


def test_prossimo_testo_automatico_ritorna_none_se_la_coda_e_vuota():
    coda = deque()

    risultato = messaggi_watcher.prossimo_testo_automatico(
        coda, ultimo_input_manuale=0.0, inizio_messaggio_corrente=None,
        ora=1000.0, idle_timeout_manuale=15.0, durata_messaggio_auto=8.0,
    )

    assert risultato is None
```

- [ ] **Step 2: Verifica che falliscano**

Run: `cd walltext && ./venv/Scripts/python.exe -m pytest tests/test_messaggi_watcher.py -v`
Expected: FAIL con `AttributeError: module 'messaggi_watcher' has no attribute 'prossimo_testo_automatico'`

- [ ] **Step 3: Implementazione minima**

Aggiungi in fondo a `walltext/messaggi_watcher.py`:

```python
def prossimo_testo_automatico(coda_auto, ultimo_input_manuale, inizio_messaggio_corrente, ora,
                               idle_timeout_manuale, durata_messaggio_auto):
    """Decide se passare al prossimo messaggio della coda automatica e lo
    rimuove da coda_auto in quel caso; altrimenti ritorna None senza
    modificare la coda.

    Condizioni, tutte necessarie:
    - sono passati almeno idle_timeout_manuale secondi dall'ultimo input
      da tastiera (qualunque esso sia stato: testo, comando, o riga vuota);
    - la coda non e' vuota;
    - non c'e' nulla in mostra (inizio_messaggio_corrente is None) oppure
      il messaggio corrente e' in mostra da almeno durata_messaggio_auto
      secondi.
    """
    if ora - ultimo_input_manuale < idle_timeout_manuale:
        return None
    if not coda_auto:
        return None
    if inizio_messaggio_corrente is not None and (ora - inizio_messaggio_corrente) < durata_messaggio_auto:
        return None
    return coda_auto.popleft()
```

- [ ] **Step 4: Verifica che passino**

Run: `cd walltext && ./venv/Scripts/python.exe -m pytest -v`
Expected: PASS (14 test)

- [ ] **Step 5: Salva**

Nessun commit (vedi Global Constraints).

---

## Task 6: Collega tutto in `TextWall.py`

**Files:**
- Modify: `walltext/TextWall.py`

**Interfaces:**
- Consumes: `messaggi_watcher.elabora_cartella`, `messaggi_watcher.prossimo_testo_automatico` (Task 4, Task 5)

Questa integrazione non è testabile in automatico (loop interattivo con terminale, socket UDP reali e finestra `cv2`, senza framework di test già presente per `TextWall.py`): si verifica a mano, come già previsto dalla spec.

- [ ] **Step 1: Aggiungi gli import**

In cima a `walltext/TextWall.py`, dopo `import queue` (riga 47), aggiungi:

```python
import os
from collections import deque

import messaggi_watcher
```

(`os` non è già importato in questo file — serve qui per `os.path.dirname`/`os.path.abspath` nel prossimo step.)

- [ ] **Step 2: Aggiungi la configurazione**

Dopo il dizionario `COLORI` (dopo la riga `}` che chiude `COLORI`, prima di `# ============================================================` / `# PREVIEW`), aggiungi:

```python
# ============================================================
# MESSAGGI AUTOMATICI (dal bridge via Bluetooth)
# ============================================================
CARTELLA_MESSAGGI = os.path.dirname(os.path.abspath(__file__))
FILE_MOSTRATI = os.path.join(CARTELLA_MESSAGGI, "mostrati.jsonl")
DURATA_MESSAGGIO_AUTO = 8.0       # secondi di permanenza di ogni messaggio
INTERVALLO_CONTROLLO_CARTELLA = 2.0   # ogni quanto guardare la cartella
IDLE_TIMEOUT_MANUALE = 15.0       # secondi dopo l'ultimo input da tastiera
```

- [ ] **Step 3: Inizializza lo stato in `main()`**

In `main()`, subito dopo la riga `testo = sys.argv[1] if len(sys.argv) > 1 else ""` (circa riga 680), aggiungi:

```python
    coda_auto = deque()
    ultimo_input_manuale = 0.0
    inizio_messaggio_corrente = None
    ultimo_controllo_cartella = 0.0
```

- [ ] **Step 4: Segna ogni input manuale**

Nel blocco `while not q.empty():` dentro il loop principale, subito dopo:

```python
                line = q.get()
                if line is None:
                    raise KeyboardInterrupt
```

aggiungi:

```python

                ultimo_input_manuale = time.time()
```

- [ ] **Step 5: Alimenta e consuma la coda automatica**

Subito dopo la chiusura del blocco `while not q.empty():` (prima del commento `# --- avanza e componi ---`), aggiungi:

```python
            # --- messaggi automatici dal bridge (Bluetooth) ---
            ora = time.time()
            if ora - ultimo_controllo_cartella >= INTERVALLO_CONTROLLO_CARTELLA:
                nuovi = messaggi_watcher.elabora_cartella(CARTELLA_MESSAGGI, FILE_MOSTRATI)
                coda_auto.extend(nuovi)
                ultimo_controllo_cartella = ora

            prossimo = messaggi_watcher.prossimo_testo_automatico(
                coda_auto, ultimo_input_manuale, inizio_messaggio_corrente, ora,
                IDLE_TIMEOUT_MANUALE, DURATA_MESSAGGIO_AUTO,
            )
            if prossimo is not None:
                testo = prossimo["text"]
                wall.set_text(testo)
                if ard:
                    ard.set_text(testo)
                inizio_messaggio_corrente = ora
                print(f"[AUTO] {testo!r}")
```

- [ ] **Step 6: Verifica manuale**

Sul Mac (o in locale se disponibile un ambiente con `opencv-python`):

```bash
cd walltext
python3 TextWall.py
```

Verifica: lo script parte senza eccezioni. Crea a mano un file di prova nella cartella dello script:

```bash
echo '{"id": 1, "text": "prova coda automatica", "created_at": "2026-09-14T10:00:00Z", "status": "delivered", "likes": 0}' > "messaggi.jsonl"
```

Aspetta fino a `INTERVALLO_CONTROLLO_CARTELLA + IDLE_TIMEOUT_MANUALE` secondi (di default, senza aver digitato nulla nel frattempo, dovrebbe bastare `INTERVALLO_CONTROLLO_CARTELLA`, dato che `ultimo_input_manuale` parte da `0.0`): il terminale deve stampare `[AUTO] 'prova coda automatica'` e il file `messaggi.jsonl` deve sparire dalla cartella, sostituito da `mostrati.jsonl` che lo contiene. Digita poi una parola a mano e premi Invio: deve prendere subito il sopravvento sulla scritta automatica.

- [ ] **Step 7: Salva**

Nessun commit (vedi Global Constraints). Se in futuro la cartella `walltext` viene messa sotto git, questo è un buon punto per un primo commit — fuori scope qui.

---

## Verifica finale

- [ ] `cd bridge && ./venv/Scripts/python.exe -m pytest -v` — tutti i test passano (bridge, inclusi Task 1 e 2)
- [ ] `cd walltext && ./venv/Scripts/python.exe -m pytest -v` — tutti i test passano (14, Task 3-5)
- [ ] Verifica manuale end-to-end reale (Pi acceso, `fetcher.py` con `MACBOOK_BT_ADDRESS`/`BT_OBEX_CHANNEL` configurate, `TextWall.py` in esecuzione sul Mac): un messaggio inviato dal form compare sul ledwall entro una decina di secondi, senza digitare nulla a mano.

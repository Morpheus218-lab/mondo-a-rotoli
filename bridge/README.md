# bridge

Client Python pensato per un secondo Raspberry Pi (collegato a un MacBook
via Bluetooth o USB — l'invio effettivo al Mac non è ancora implementato,
vedi "Fuori scope" sotto). Ogni 5 secondi interroga lo storico pubblico
dell'hosting (`hosting/api/history.php`) e salva in locale, in un file di
testo formato [JSON Lines](https://jsonlines.org/), i messaggi consegnati
che non aveva ancora visto.

Non chiama mai `claim.php`/`ack.php`: quegli endpoint sono riservati al
Raspberry Pi della stampante (segnano un messaggio come "in stampa" — se
il bridge li chiamasse, ruberebbe messaggi dalla coda di stampa). Il
bridge non richiede nessuna API key: legge solo l'endpoint pubblico di
storico, già usato dal frontend.

## Configurazione

Crea un file `.env` (non committato, vedi `.gitignore`) nella cartella
`bridge/` con:

```
API_BASE_URL=https://TUO_DOMINIO/api
OUTPUT_FILE=messaggi.jsonl
```

`OUTPUT_FILE` è opzionale (default `messaggi.jsonl`, nella working
directory del processo).

## Formato del file di output

Una riga JSON per messaggio, nell'ordine in cui sono stati scoperti (dal
più vecchio al più nuovo), con gli stessi campi restituiti da
`history.php` (`id`, `text`, `created_at`, `status`, `likes`):

```
{"id": 41, "text": "ciao mondo", "created_at": "2026-09-14T10:32:00Z", "status": "delivered", "likes": 2}
{"id": 42, "text": "un altro messaggio", "created_at": "2026-09-14T10:32:05Z", "status": "delivered", "likes": 0}
```

Al primo avvio (nessun file precedente) il bridge salva tutti i messaggi
trovati nella prima pagina di storico (fino a 100, il massimo
consentito da `history.php`); se al momento del primo avvio ci sono già
più di 100 messaggi consegnati, quelli più vecchi non vengono recuperati
retroattivamente (limite noto, vedi "Fuori scope").

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
python3 fetcher.py
```

## Esecuzione in produzione (systemd)

```bash
sudo cp mondo-a-rotoli-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mondo-a-rotoli-bridge
```

Il file assume che il repository sia clonato in `/home/pi/mondo-a-rotoli`
e il file `.env` si trovi in `/home/pi/mondo-a-rotoli/bridge/.env`;
adattare i percorsi nel file `.service` se diversi. Log del servizio:
`journalctl -u mondo-a-rotoli-bridge -f`.

## Fuori scope (per ora)

- Invio dei messaggi salvati al MacBook via Bluetooth o USB — questo
  script si ferma al file locale; il ponte verso il Mac è un passo
  successivo.
- Recupero retroattivo di messaggi consegnati oltre la prima pagina di
  storico (100) se il bridge parte per la prima volta quando ne esistono
  già di più.
- Rotazione/pulizia del file di output: cresce senza limiti nel tempo.

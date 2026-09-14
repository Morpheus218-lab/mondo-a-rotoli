# bridge

Client Python pensato per un secondo Raspberry Pi (collegato a un MacBook
via Bluetooth o USB). Ogni 5 secondi interroga lo storico pubblico
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
OUTPUT_FILE=/home/pi/mondo-a-rotoli/bridge/messaggi.jsonl
MACBOOK_BT_ADDRESS=A4:CF:99:61:92:F8
BT_OBEX_CHANNEL=10
```

`OUTPUT_FILE` è opzionale (default `messaggi.jsonl`, risolto rispetto
alla working directory del processo — con il servizio systemd incluso
questa è la root del repository, non `bridge/`: per questo conviene
usare un percorso assoluto in `.env` invece di lasciare il default).

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

### Integrazione con il Mac (TextWall)

Due cose devono corrispondere esattamente tra il Pi e il Mac perché
l'invio via Bluetooth arrivi davvero a destinazione, e nessuna delle due
viene validata automaticamente — se sbagliate, il trasferimento "riesce"
lato bridge ma il muro non mostra mai nulla:

- la cartella per gli elementi ricevuti della Condivisione Bluetooth sul
  Mac (System Preferences → Condivisione → Condivisione Bluetooth) deve
  essere impostata esattamente sulla cartella in cui si trova
  `TextWall.py` sul Mac: `TextWall.py` calcola la cartella da
  monitorare come la cartella dello script stesso, quindi se la
  Condivisione Bluetooth è puntata altrove (es. il Desktop) i file
  arrivano ma il muro non li vedrà mai;
- il nome del file indicato in `OUTPUT_FILE` (sul Pi) deve avere un nome
  che corrisponde al pattern `messaggi*.jsonl`: è quello che
  `messaggi_watcher.py` (sul Mac) usa per trovare i file in arrivo. Se
  viene rinominato in qualcos'altro, obexftp segnala comunque il
  trasferimento come riuscito, ma il muro non lo raccoglierà mai.

## Formato del file di output

Una riga JSON per messaggio, nell'ordine in cui sono stati scoperti (dal
più vecchio al più nuovo), con gli stessi campi restituiti da
`history.php` (`id`, `text`, `created_at`, `status`, `likes`):

```
{"id": 41, "text": "ciao mondo", "created_at": "2026-09-14T10:32:00Z", "status": "delivered", "likes": 2}
{"id": 42, "text": "un altro messaggio", "created_at": "2026-09-14T10:32:05Z", "status": "delivered", "likes": 0}
```

`history.php` restituisce al massimo 100 messaggi per chiamata (i più
recenti). Questo non riguarda solo il primo avvio: se il bridge resta
fermo abbastanza a lungo (Pi spento, hosting irraggiungibile) da
accumulare più di 100 messaggi consegnati nel frattempo, quelli più
vecchi della finestra dei 100 più recenti non vengono recuperati
retroattivamente e restano assenti dal file locale (limite noto, vedi
"Fuori scope").

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

- Recupero retroattivo di messaggi consegnati rimasti fuori dalla
  finestra dei 100 più recenti restituiti da `history.php` (non solo al
  primo avvio: anche dopo una pausa prolungata del bridge).
- Rotazione/pulizia del file di output: cresce senza limiti nel tempo.

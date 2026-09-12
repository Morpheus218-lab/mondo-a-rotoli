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
`USBError: [Errno 13] Access denied`), serve una regola udev che dia
all'utente `pi` accesso al dispositivo della stampante (vendor/product ID
definiti in `printer.py`, `Usb(0x0416, 0x5011, ...)`).

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

## Messaggi bloccati in stato "printing"

Se il poller si interrompe tra un claim riuscito e la conferma, un
messaggio può restare bloccato in stato `printing` sull'hosting. Questo è
voluto (evita il rischio di doppie stampe): vedi
`../hosting/README.md` per la procedura di sblocco manuale.

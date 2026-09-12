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

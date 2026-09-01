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

## Esecuzione in produzione (systemd)

L'avvio manuale sopra è utile per sviluppo e debug, ma non sopravvive alla
chiusura della sessione SSH o a un riavvio del Pi. Per la produzione,
usare il servizio systemd incluso (`txtinstallazione.service`), che riavvia
automaticamente il processo in caso di crash — necessario perché il
recupero dei messaggi `pending` avviene "al prossimo avvio del processo".

```bash
sudo cp txtinstallazione.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now txtinstallazione
```

Il file assume che il progetto sia clonato in `/home/pi/txtinstallazione`
con il virtualenv in `venv/`; adattare i percorsi nel file `.service` se
diversi. Log del servizio: `journalctl -u txtinstallazione -f`.

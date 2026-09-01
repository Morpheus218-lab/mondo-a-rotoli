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

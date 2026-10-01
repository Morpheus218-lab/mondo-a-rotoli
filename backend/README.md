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

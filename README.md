# mondo-a-rotoli

Installazione interattiva: una pagina web dove le persone scrivono un
messaggio, che viene stampato su carta da una stampante USB collegata a un
Raspberry Pi Zero.

## Come far partire l'installazione

Per accendere tutto servono due cose, in ordine: **mettere online il sito**
e **accendere il Raspberry Pi con la stampante collegata**.

### 1. Metti online il sito

- Carica il contenuto delle cartelle `frontend/` e `hosting/api/` sul tuo
  hosting (dominio unico, es. `mondoarotoli.cuoredinapoli.net`).
- Crea un database MySQL vuoto e importa lo schema che trovi in
  `hosting/schema.sql` (con phpMyAdmin basta aprirlo e premere "Esegui").
- Copia il file `hosting/api/config.php.example`, rinomina la copia in
  `config.php` e scrivici dentro le credenziali del database e una
  password segreta a tua scelta (è la "chiave" che userà anche il Pi per
  parlare col sito).
- Apri il sito nel browser: deve comparire la pagina con il campo per
  scrivere il messaggio.

Tutti i comandi passo per passo sono in [`hosting/README.md`](hosting/README.md).

### 2. Accendi il Raspberry Pi

- Collega la stampante al Pi via USB e controlla che ci sia carta.
- Sul Pi, crea un file chiamato `.env` dentro la cartella `backend/` e
  scrivici l'indirizzo del sito e la stessa password segreta scelta al
  punto 1.
- Avvia il programma con `python3 poller.py`, oppure — meglio, così
  riparte da solo a ogni riavvio del Pi — attiva il servizio automatico
  descritto nel README del backend.
- Da quel momento il Pi controlla il sito ogni 5 secondi: appena qualcuno
  scrive un messaggio, esce stampato in automatico.

Tutti i comandi passo per passo sono in [`backend/README.md`](backend/README.md).

### 3. Prova che funzioni

Scrivi un messaggio di prova dal sito: entro 5 secondi deve uscire dalla
stampante. Se non succede, controlla nell'ordine: il Pi è acceso ed è
connesso a internet, la stampante è collegata e ha carta, la password nel
file `.env` del Pi è identica a quella scritta in `config.php` sul sito.

## Come funziona

Il sistema è diviso in tre parti, che girano su due macchine diverse:

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│   Hosting condiviso      │        │   Raspberry Pi Zero           │
│   (es. cuoredinapoli)    │        │   (a casa/studio, no IP       │
│                          │        │    pubblico, dietro NAT)      │
│  frontend/index.html    │        │                                │
│      (pagina statica)   │        │  backend/poller.py             │
│           │              │        │      │                        │
│           ▼              │        │      ▼                        │
│  hosting/api/*.php      │◄───────┼──── ogni 5 secondi, HTTP       │
│      + tabella MySQL    │───────►│      (claim → stampa → ack)    │
│                          │        │      │                        │
└─────────────────────────┘        │      ▼                        │
                                    │  backend/printer.py            │
                                    │      │                        │
                                    │      ▼                        │
                                    │  stampante termica USB         │
                                    └──────────────────────────────┘
```

1. Un visitatore scrive un messaggio su **`frontend/index.html`**, che lo
   invia con `POST` a **`hosting/api/message.php`**. Il messaggio finisce
   in una tabella MySQL con stato `pending`.
2. Il **Raspberry Pi** non riceve mai richieste da internet — non è mai
   raggiungibile dall'esterno, il che evita di dover configurare port
   forwarding o un dominio per il Pi. È lui che, ogni 5 secondi, chiama
   verso l'esterno **`hosting/api/claim.php`** chiedendo "c'è qualcosa da
   stampare?". Se c'è, quel messaggio passa allo stato `printing` e viene
   restituito al Pi.
3. Il Pi stampa il messaggio con **`backend/printer.py`** sulla stampante
   USB collegata.
4. Se la stampa riesce, il Pi chiama **`hosting/api/ack.php`** per
   confermarla: il messaggio passa a `delivered` e compare nello storico
   pubblico (`hosting/api/history.php`, mostrato in
   `frontend/index.html`).

Un messaggio passato a `printing` **non torna mai automaticamente
`pending`**: se qualcosa va storto tra il claim e la conferma (stampante
scollegata, Pi che si riavvia, rete a singhiozzo), il messaggio resta
bloccato lì finché non viene sbloccato a mano — per scelta, così da non
rischiare mai di stampare due volte lo stesso messaggio. La procedura di
sblocco è in [`hosting/README.md`](hosting/README.md#sblocco-manuale-di-un-messaggio-bloccato-in-printing).

## Struttura del repository — quale file va dove

Il repository contiene il codice di **entrambe** le macchine: in fase di
deploy, cartelle diverse finiscono su macchine diverse.

| Cartella nel repo | Va deployata su | Contiene |
|---|---|---|
| [`frontend/`](frontend/) | Hosting condiviso, root del sito | `index.html` (pagina principale: invio + storico), `storico.html` (solo storico, sola lettura) |
| [`hosting/api/`](hosting/api/) | Hosting condiviso, dentro `api/` | Gli endpoint PHP (`message.php`, `history.php`, `claim.php`, `ack.php`) + `db.php` (funzioni condivise) + `config.php` (credenziali, **non committato**, va creato copiando `config.php.example`) |
| [`hosting/schema.sql`](hosting/schema.sql) | Hosting condiviso, eseguito una volta sul database MySQL | Schema della tabella `messaggi` |
| [`backend/`](backend/) | Raspberry Pi (stampante) | `poller.py` (loop principale), `api_client.py` (chiamate HTTP), `printer.py` (stampa), `.env` (config, **non committato**), `mondo-a-rotoli.service` (systemd) |
| [`bridge/`](bridge/) | Secondo Raspberry Pi (opzionale, collegato a un MacBook) | `fetcher.py` (loop principale), `api_client.py` (chiamate HTTP), `bluetooth_sender.py` (invio via obexftp), `.env` (config, **non committato**), `mondo-a-rotoli-bridge.service` (systemd) |
| [`ledwall/`](ledwall/) | MacBook (opzionale, collegato al Pi #2 via Bluetooth) | `TextWall.py` (loop principale, scrive sul ledwall via UDP), `messaggi_watcher.py` (legge i file ricevuti dal Pi #2), `mostrati.jsonl` (stato/archivio, **non committato**, creato al primo avvio) |

Niente, in questo repo, gira sull'hosting E su un Pi contemporaneamente: ogni
cartella ha una sola destinazione. `docs/` non va deployato da nessuna
parte — contiene solo la documentazione di design del progetto.

Le istruzioni di deploy dettagliate, passo per passo, sono nei README di
ciascuna parte:

- [`hosting/README.md`](hosting/README.md) — deploy del backend PHP +
  MySQL e del frontend, endpoint esposti, checklist di test manuale.
- [`backend/README.md`](backend/README.md) — configurazione e avvio del
  poller sul Raspberry Pi, esecuzione come servizio systemd.
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

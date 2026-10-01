# mondo-a-rotoli

Installazione interattiva: una pagina web dove le persone scrivono un
messaggio, che viene stampato su carta da una o più stampanti USB
collegate ad altrettanti Raspberry Pi.

## Come far partire l'installazione

Per accendere tutto servono due cose, in ordine: **mettere online il sito**
e **accendere ogni Raspberry Pi con la sua stampante collegata**.

### 1. Metti online il sito

- Carica il contenuto delle cartelle `frontend/` e `hosting/api/` sul tuo
  hosting (dominio unico, es. `mondoarotoli.cuoredinapoli.net`).
- Crea un database MySQL vuoto e importa lo schema che trovi in
  `hosting/schema.sql` (con phpMyAdmin basta aprirlo e premere "Esegui").
- Copia il file `hosting/api/config.php.example`, rinomina la copia in
  `config.php` e scrivici dentro le credenziali del database.
- Apri il sito nel browser: deve comparire la pagina con il campo per
  scrivere il messaggio.

Tutti i comandi passo per passo sono in [`hosting/README.md`](hosting/README.md).

### 2. Accendi ogni Raspberry Pi

Ripeti questi passaggi su **ogni** Pi stampante: ognuno stampa in
autonomia tutti i messaggi, senza bisogno di coordinarsi con gli altri.

- Collega la stampante al Pi via USB e controlla che ci sia carta.
- Sul Pi, crea un file chiamato `.env` dentro la cartella `backend/` e
  scrivici l'indirizzo del sito (facoltativo un nome per distinguere
  questo Pi nei log).
- Avvia il programma con `python3 poller.py`, oppure — meglio, così
  riparte da solo a ogni riavvio del Pi — attiva il servizio automatico
  descritto nel README del backend.
- Al primo avvio il Pi non stampa nulla dei messaggi già esistenti:
  solo da quel momento in poi stampa ciò che arriva di nuovo, ogni 5
  secondi.

Tutti i comandi passo per passo sono in [`backend/README.md`](backend/README.md).

### 3. Prova che funzioni

Scrivi un messaggio di prova dal sito: entro 5 secondi deve uscire da
**tutte** le stampanti collegate. Se non succede su una di loro,
controlla nell'ordine: quel Pi è acceso ed è connesso a internet, la
stampante è collegata e ha carta, `API_BASE_URL` nel suo `.env` è
corretto.

## Come funziona

Il sistema è diviso in due parti: l'hosting condiviso, e N Raspberry Pi
stampanti indipendenti fra loro.

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│   Hosting condiviso      │        │   Raspberry Pi stampante #1   │
│   (es. cuoredinapoli)    │        │   (a casa/studio, no IP       │
│                          │   ┌───►│    pubblico, dietro NAT)      │
│  frontend/index.html    │   │    │  backend/poller.py             │
│      (pagina statica)   │   │    │      │ ogni 5s, GET history.php│
│           │              │   │    │      ▼                        │
│           ▼              │   │    │  backend/printer.py            │
│  hosting/api/*.php      │   │    │      │                        │
│      + tabella MySQL    │───┤    │      ▼                        │
│                          │   │    │  stampante termica USB         │
│                          │   │    └──────────────────────────────┘
│                          │   │    ┌──────────────────────────────┐
│                          │   └───►│   Raspberry Pi stampante #2    │
│                          │        │   (stessa logica, in un altro  │
└─────────────────────────┘        │    luogo, indipendente dal #1) │
                                    └──────────────────────────────┘
```

1. Un visitatore scrive un messaggio su **`frontend/index.html`**, che lo
   invia con `POST` a **`hosting/api/message.php`**. Il messaggio finisce
   subito in una tabella MySQL con stato `delivered` e compare
   immediatamente nello storico pubblico (`hosting/api/history.php`,
   mostrato in `frontend/index.html`).
2. Ogni **Raspberry Pi stampante** non riceve mai richieste da internet —
   non è mai raggiungibile dall'esterno, il che evita di dover
   configurare port forwarding o un dominio per il Pi. È lui che, ogni 5
   secondi, chiama verso l'esterno **`hosting/api/history.php`** e
   confronta la risposta con un elenco che tiene in locale di cosa ha
   già stampato.
3. Ogni messaggio mai visto prima viene stampato con
   **`backend/printer.py`** sulla stampante USB collegata a quel Pi, e
   registrato nell'elenco locale solo dopo la stampa riuscita — se la
   stampa fallisce, il messaggio resta "da stampare" e viene ritentato
   automaticamente al ciclo successivo, senza bisogno di nessun
   intervento manuale.

Ogni Pi è completamente indipendente dagli altri: lo stesso messaggio
viene stampato da **tutte** le stampanti collegate, non da una sola.

## Struttura del repository — quale file va dove

Il repository contiene il codice di **tutte** le macchine coinvolte: in
fase di deploy, cartelle diverse finiscono su macchine diverse.

| Cartella nel repo | Va deployata su | Contiene |
|---|---|---|
| [`frontend/`](frontend/) | Hosting condiviso, root del sito | `index.html` (pagina principale: invio + storico), `storico.html` (solo storico, sola lettura) |
| [`hosting/api/`](hosting/api/) | Hosting condiviso, dentro `api/` | Gli endpoint PHP (`message.php`, `history.php`, `like.php`) + `db.php` (funzioni condivise) + `config.php` (credenziali, **non committato**, va creato copiando `config.php.example`) |
| [`hosting/schema.sql`](hosting/schema.sql) | Hosting condiviso, eseguito una volta sul database MySQL | Schema della tabella `messaggi` |
| [`backend/`](backend/) | Ogni Raspberry Pi stampante (uno o più, indipendenti tra loro) | `poller.py` (loop principale), `api_client.py` (chiamate HTTP), `printer.py` (stampa), `.env` (config, **non committato**), `mondo-a-rotoli.service` (systemd) |
| [`bridge/`](bridge/) | Raspberry Pi opzionale, collegato a un MacBook | `fetcher.py` (loop principale), `api_client.py` (chiamate HTTP), `bluetooth_sender.py` (invio via obexftp), `.env` (config, **non committato**), `mondo-a-rotoli-bridge.service` (systemd) |
| [`ledwall/`](ledwall/) | MacBook opzionale, collegato via Bluetooth | `TextWall.py` (loop principale, scrive sul ledwall via UDP), `messaggi_watcher.py` (legge i file ricevuti), `mostrati.jsonl` (stato/archivio, **non committato**, creato al primo avvio) |

Niente, in questo repo, gira sull'hosting E su un Pi contemporaneamente: ogni
cartella ha una sola destinazione. `docs/` non va deployato da nessuna
parte — contiene solo la documentazione di design del progetto.

Le istruzioni di deploy dettagliate, passo per passo, sono nei README di
ciascuna parte:

- [`hosting/README.md`](hosting/README.md) — deploy del backend PHP +
  MySQL e del frontend, endpoint esposti, checklist di test manuale.
- [`backend/README.md`](backend/README.md) — configurazione e avvio del
  poller su ogni Raspberry Pi stampante, esecuzione come servizio
  systemd, come aggiungerne uno nuovo.
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

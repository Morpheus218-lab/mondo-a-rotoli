# mondo-a-rotoli

Installazione interattiva: una pagina web dove le persone scrivono un
messaggio, che viene stampato su carta da una stampante USB collegata a un
Raspberry Pi Zero.

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
| [`frontend/`](frontend/) | Hosting condiviso, root del sito | `index.html`, la pagina statica che i visitatori vedono |
| [`hosting/api/`](hosting/api/) | Hosting condiviso, dentro `api/` | Gli endpoint PHP (`message.php`, `history.php`, `claim.php`, `ack.php`) + `db.php` (funzioni condivise) + `config.php` (credenziali, **non committato**, va creato copiando `config.php.example`) |
| [`hosting/schema.sql`](hosting/schema.sql) | Hosting condiviso, eseguito una volta sul database MySQL | Schema della tabella `messaggi` |
| [`backend/`](backend/) | Raspberry Pi | `poller.py` (loop principale), `api_client.py` (chiamate HTTP), `printer.py` (stampa), `.env` (config, **non committato**), `txtinstallazione.service` (systemd) |

Niente, in questo repo, gira sull'hosting E sul Pi contemporaneamente: ogni
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

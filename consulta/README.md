# consulta

Client Python che ogni 10 secondi interroga lo storico pubblico di
un'installazione "consulta" (stesso schema/endpoint di
`hosting/api/history.php`, ma un dominio/database **diverso** da quello
usato da `backend/`, `bridge/` e `ledwall/` per i messaggi stampati).
Ogni messaggio mai visto viene passato a un modello locale via
[Ollama](https://ollama.com/) per generare almeno 2 tag, poi scritto in
testa a `Consulta.md`, cosi' che i messaggi piu' recenti restino sempre
in cima al file (ordine cronologico decrescente).

A differenza di `backend/poller.py`, al primo avvio `consulta` tagga e
scrive anche tutto il backlog recuperabile (fino a 100 messaggi), non
solo quelli arrivati da quel momento in poi.

Opzionalmente, `consulta` puo' anche pubblicare `Consulta.md` su un
repository git remoto (vedi "Pubblicazione su repo remoto" sotto),
sostituendo il file con lo stesso nome nella root di quel repo ad ogni
aggiornamento.

## Formato di Consulta.md

Un blocco per messaggio, dal piu' recente al meno recente:

```
[[saluti]], [[amicizia]]
ciao a tutti, bellissima installazione!

[[arte]], [[riflessione]]
un messaggio piu' vecchio
```

## Configurazione

Serve un'istanza di Ollama raggiungibile (in locale o in rete) con il
modello scaricato:

```bash
ollama pull llama3.1:8b
```

Crea un file `.env` (non committato, vedi `.gitignore`) nella cartella
`consulta/` con:

```
API_BASE_URL=https://DOMINIO_CONSULTA/api
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
STATO_FILE=/percorso/assoluto/consulta/taggati.jsonl
CONSULTA_FILE=/percorso/assoluto/consulta/Consulta.md
```

`API_BASE_URL` punta all'installazione "consulta" (dominio/database
diverso da quello dei messaggi stampati, ma stesso endpoint
`history.php`). `OLLAMA_HOST`, `OLLAMA_MODEL`, `STATO_FILE` e
`CONSULTA_FILE` sono opzionali (default sopra riportati, risolti
rispetto alla working directory del processo — con il servizio systemd
incluso questa e' la root del repository, non `consulta/`: per questo
conviene usare percorsi assoluti in `.env` invece di lasciare i
default).

## Pubblicazione su repo remoto (opzionale)

Se configurata, ad ogni ciclo `consulta` controlla se sono passati
almeno `CONSULTA_REMOTE_PUSH_INTERVALLO_SECONDI` secondi dall'ultimo
tentativo e, in caso affermativo, aggiorna un clone locale del repo
remoto, ci copia sopra `Consulta.md` e — solo se il contenuto e'
cambiato — fa commit e push. Se la pubblicazione fallisce (rete,
autenticazione, conflitto) l'errore viene loggato e si riprova al giro
successivo, senza bloccare il tagging dei nuovi messaggi.

Aggiungi in `.env`:

```
CONSULTA_REMOTE_URL=git@host:utente/nome-repo.git
CONSULTA_REMOTE_BRANCH=main
CONSULTA_REMOTE_PUSH_INTERVALLO_SECONDI=10
CONSULTA_REMOTE_CLONE_DIR=/percorso/assoluto/consulta/remote-consulta
```

Solo `CONSULTA_REMOTE_URL` e' obbligatoria per attivare la
pubblicazione: se assente, questa parte resta disattivata e `consulta`
si comporta come senza repo remoto. `CONSULTA_REMOTE_BRANCH` (default
`main`) e `CONSULTA_REMOTE_PUSH_INTERVALLO_SECONDI` (default 10, in
secondi) sono opzionali. `CONSULTA_REMOTE_CLONE_DIR` e' opzionale
(default `consulta/remote-consulta/`, non committato — vedi
`.gitignore`); il clone viene creato automaticamente al primo giro se
non esiste ancora.

Perche' il push funzioni senza interazione serve, sulla macchina che fa
girare `watcher.py`:

- una chiave SSH gia' autorizzata a fare push su `CONSULTA_REMOTE_URL`
  (es. una deploy key con permessi di scrittura, caricata in un
  `ssh-agent` attivo per l'utente che esegue il servizio);
- `git config --global user.name` e `user.email` gia' impostati
  (servono per creare i commit — `git commit` fallisce senza).

## Sviluppo locale

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

## Avvio

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)
python3 watcher.py
```

## Esecuzione in produzione (systemd)

```bash
sudo cp mondo-a-rotoli-consulta.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now mondo-a-rotoli-consulta
```

Il file assume che il repository sia clonato in
`/home/pi/mondo-a-rotoli` e il file `.env` si trovi in
`/home/pi/mondo-a-rotoli/consulta/.env`; adattare i percorsi nel file
`.service` se diversi. Log del servizio:
`journalctl -u mondo-a-rotoli-consulta -f`.

## Fuori scope (per ora)

- Recupero retroattivo di messaggi rimasti fuori dalla finestra dei 100
  piu' recenti restituiti da `history.php` (non solo al primo avvio:
  anche dopo una pausa prolungata di `consulta`).
- Rotazione/pulizia di `Consulta.md` e `STATO_FILE`: crescono senza
  limiti nel tempo.
- Rigenerazione dei tag per messaggi gia' taggati (se il modello
  cambia, il backlog gia' scritto non viene ritaggato).

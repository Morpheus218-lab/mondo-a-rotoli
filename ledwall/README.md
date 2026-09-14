# ledwall

Script Python che gira sul MacBook e scrive testo scorrevole su un ledwall
fisico via UDP ([`TextWall.py`](TextWall.py)). Riceve i messaggi in due modi
che convivono:

- **da tastiera**, digitando e premendo Invio nel terminale dove gira lo
  script (comportamento originale, sempre disponibile);
- **in automatico**, dal [Pi #2](../bridge/) via Bluetooth: ogni ~2 secondi
  ([`messaggi_watcher.py`](messaggi_watcher.py)) controlla la propria
  cartella per i file `messaggi*.jsonl` ricevuti, ne estrae i messaggi mai
  visti (dedup per insieme-di-id contro un archivio permanente
  `mostrati.jsonl`, creato al primo avvio) e li mette in coda, uno alla
  volta per 8 secondi ciascuno, cancellando i file sorgente dopo averli
  letti.

L'input manuale ha sempre precedenza immediata: se digiti qualcosa, la coda
automatica si ferma e riprende da sola 15 secondi dopo che smetti di
scrivere.

Il canale "in automatico" è opzionale e non richiede nulla se non ti serve:
se nessun file arriva mai nella cartella, lo script funziona esattamente
come prima (solo tastiera).

## Requisiti per far funzionare l'automatico

Due cose devono corrispondere esattamente tra il Pi e il Mac (documentate
anche in [`bridge/README.md`](../bridge/README.md#integrazione-con-il-mac-textwall)),
altrimenti l'invio "riesce" dal lato del Pi ma il muro non mostra mai
nulla, senza errori visibili:

- la cartella per gli elementi ricevuti della **Condivisione Bluetooth**
  del Mac (Impostazioni di Sistema → Generali → Condivisione →
  Condivisione Bluetooth) deve essere impostata esattamente sulla cartella
  in cui si trova questo `TextWall.py` — lo script guarda solo la propria
  cartella, non l'intera Scrivania;
- il Pi deve avere `MACBOOK_BT_ADDRESS`/`BT_OBEX_CHANNEL` configurati nel
  suo `.env` e il pairing Bluetooth già fatto (vedi il README del bridge).

## Installazione sul Mac

Sul Mac ci sono più Python installati: quello di default (3.9) è vuoto,
usa il 3.13.

```bash
cd ledwall
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m pip install -r requirements.txt
```

## Avvio

```bash
cd ledwall
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 TextWall.py
```

Comandi da terminale (invariati, vedi anche l'intestazione del file):
scrivi un testo e premi Invio per mandarlo sul muro, riga vuota per
spegnerlo, `:c`/`:s`/`:f`/`:r`/`:m`/`:v`/`:a`/`:d`/`:i`/`:h`/`:q` per
colore/velocità/fps/direzione/specchio/appello/collaudo/inversione/
aiuto/uscita.

## File generati a runtime (non committati)

- `mostrati.jsonl` — archivio permanente di tutti i messaggi già mostrati
  (usato per la dedup, cresce senza limiti nel tempo, va aggiunto a
  `.gitignore` se questa cartella viene clonata su altre macchine).

## Sviluppo locale

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
pytest -v
```

`messaggi_watcher.py` è testato ([`tests/`](tests/)) perché sono funzioni
pure. `TextWall.py` non ha test automatici: è un loop interattivo con
terminale, socket UDP reali e finestra `cv2` — non facilmente testabile
senza hardware. Le modifiche a `TextWall.py` vanno verificate a mano.

## Fuori scope (per ora)

- Interfaccia per riordinare o rimuovere manualmente messaggi già
  accodati.
- Rotazione/pulizia di `mostrati.jsonl`.
- Test automatici per `TextWall.py` (vedi sopra).

# Invio automatico dei messaggi dal Pi #2 al ledwall via Bluetooth — design

Data: 2026-09-14

## Contesto

Il Pi #2 ([bridge/](../../../bridge/)) interroga già ogni 5 secondi lo storico
pubblico dell'hosting e salva in locale, in `messaggi.jsonl`, i messaggi
consegnati non ancora visti (vedi
[2026-09-01-backend-raspberry-design.md](2026-09-01-backend-raspberry-design.md)
e il README di `bridge/`). Il Pi #2 è accoppiato via Bluetooth classico con
un MacBook (nome Bluetooth `NTA11`, indirizzo `A4:CF:99:61:92:F8`) su cui
gira [TextWall.py](file:///C:/Users/alph2/OneDrive/WINZOZ_S/Documents/Project/walltext/TextWall.py)
— un progetto separato, non in questo repository, cartella
`~/Desktop/WallText` sul Mac — che scrive testo scorrevole su un ledwall via
UDP. Oggi TextWall.py prende il testo solo da tastiera (`input()` in un
thread); non esiste ancora nessuna automazione.

Test manuali già fatti e confermati:
- Invio di un file al Mac via OBEX Object Push (`obexftp -b <MAC> -B 10 -p
  <file>`, canale scoperto con `sdptool browse`), con successo nonostante il
  comando termini con "Disconnecting...failed" (dettaglio noto di
  `obexftp`: il Mac chiude la connessione OBEX subito dopo il trasferimento,
  prima della disconnessione esplicita — il file arriva comunque).
- La Condivisione Bluetooth di macOS **non sovrascrive** un file con lo
  stesso nome già presente: lo rinomina (`messaggi.jsonl`, `messaggi
  #1.jsonl`, `messaggi #2.jsonl`, ...). Non esiste un'opzione per
  disattivare questo comportamento.

## Obiettivo

- Il Pi #2 manda automaticamente `messaggi.jsonl` al Mac via Bluetooth ogni
  volta che un ciclo di polling ha scritto messaggi nuovi (stesso ritmo del
  poll, ~5s quando c'è roba nuova).
- Sul Mac, `TextWall.py` scopre da solo i file ricevuti, ne estrae i
  messaggi mai visti, li mette in coda e li mostra sul muro uno alla volta.
- I file duplicati numerati da macOS vengono ripuliti subito dopo la
  lettura: la cartella non accumula nulla nel tempo.
- L'input manuale da terminale resta sempre disponibile e ha precedenza
  immediata sui messaggi automatici.

## Architettura

```
bridge/fetcher.py (Pi #2)                    TextWall.py (MacBook)
  ogni 5s: poll history.php                     ogni ~2s: guarda la cartella
  -> append nuovi in messaggi.jsonl              per file messaggi*.jsonl arrivati
  -> se ha aggiunto qualcosa:                    per ciascuno (dal piu' vecchio):
     invia l'intero file via obexftp               estrae i messaggi con id
     (canale 10, Object Push) al Mac                mai visti prima (stesso
                                                      algoritmo a insieme-di-id
                                                      gia' usato in fetcher.py)
                                                    li accoda, poi CANCELLA il file
                                                  la coda si smaltisce un
                                                  messaggio alla volta sul muro,
                                                  N secondi ciascuno
```

Il file che il Pi manda è **cumulativo** (contiene tutta la cronologia
salvata finora, non solo il delta di questo ciclo), perché è lo stesso
`messaggi.jsonl` che si allunga sempre — non viene mai troncato. Ogni invio
quindi ripropone anche messaggi già mandati in cicli precedenti: non è un
problema, perché il Mac tiene un proprio archivio permanente
(`mostrati.jsonl`) con gli id già messi in coda, e lo stesso algoritmo di
dedup per insieme-di-id già scritto e testato in `bridge/fetcher.py` scarta
tutto ciò che è già stato visto. Quell'archivio funge insieme da stato di
dedup e da storico di tutto ciò che è passato sul muro.

## Componenti

### `bridge/bluetooth_sender.py` (nuovo)

```python
def invia_file(path, indirizzo_mac, canale) -> bool
```

Lancia `obexftp -b <indirizzo_mac> -B <canale> -p <path>` via `subprocess`
e ritorna `True`/`False`. Il successo **non** si legge dal codice di uscita
del processo (può essere diverso da zero per il "Disconnecting...failed"
noto), ma cercando nell'output una riga tipo `Sending "...".../done`.
Se quella riga non c'è, l'invio è considerato fallito.

### `bridge/fetcher.py` (modificato)

Dopo che `process_one_ciclo` ha scritto righe nuove in `output_path`, se le
variabili d'ambiente `MACBOOK_BT_ADDRESS` e `BT_OBEX_CHANNEL` sono
configurate chiama `bluetooth_sender.invia_file`. Se non sono configurate,
l'invio Bluetooth viene saltato silenziosamente (loggato una volta a
livello INFO all'avvio) — il bridge resta usabile anche senza Bluetooth
accoppiato, come oggi. Se `invia_file` ritorna `False` o solleva
un'eccezione, viene loggato un errore e il ciclo prosegue normalmente: il
file resta comunque aggiornato in locale e, essendo cumulativo, verrà
proposto per intero al prossimo invio riuscito — nessun messaggio viene
perso, solo ritardato.

### `walltext/messaggi_watcher.py` (nuovo, progetto Mac)

Funzioni pure, mirror di quelle già in `bridge/fetcher.py`:

- `trova_file_messaggi(cartella)` — lista dei path che combaciano con
  `messaggi*.jsonl`, ordinata per data di modifica crescente.
- `carica_id_mostrati(file_stato)` — insieme degli id già presenti in
  `mostrati.jsonl` (righe non leggibili ignorate con warning, stesso
  comportamento di `_leggi_id_gia_salvati` in `bridge/fetcher.py`).
- `estrai_nuovi(path, id_gia_mostrati)` — messaggi del file con id non in
  `id_gia_mostrati`, ordinati dal più vecchio al più nuovo.
- `elabora_cartella(cartella, file_stato)` — per ogni file trovato (nel
  loro ordine), estrae i nuovi, li appende a `mostrati.jsonl`, cancella il
  file sorgente. Ritorna la lista di tutti i messaggi nuovi trovati, in
  ordine.

### `TextWall.py` (modificato)

Nuove costanti di configurazione:

```python
CARTELLA_MESSAGGI = Path(__file__).parent      # dove arrivano i file Bluetooth
FILE_MOSTRATI = CARTELLA_MESSAGGI / "mostrati.jsonl"
DURATA_MESSAGGIO_AUTO = 8.0     # secondi di permanenza di ogni messaggio in coda
INTERVALLO_CONTROLLO_CARTELLA = 2.0   # ogni quanto guardare la cartella
IDLE_TIMEOUT_MANUALE = 15.0     # secondi dopo l'ultimo input manuale prima che l'automatico riprenda
```

Nel loop principale: un controllo a tempo (non a ogni frame) chiama
`messaggi_watcher.elabora_cartella` e accoda il risultato in un
`collections.deque` in memoria (`coda_auto`). A ogni iterazione del loop:

- se sono passati meno di `IDLE_TIMEOUT_MANUALE` secondi dall'ultimo input
  da tastiera (digitare testo, un comando `:x`, o anche una riga vuota per
  spegnere), l'automatico non tocca nulla — l'input manuale vince sempre;
- altrimenti, se `coda_auto` non è vuota e il messaggio automatico
  corrente è in mostra da almeno `DURATA_MESSAGGIO_AUTO` secondi (o non
  c'è nulla in mostra), si estrae il prossimo dalla coda e si chiama
  `wall.set_text(...)`.

Qualunque input da tastiera aggiorna il timestamp "ultimo input manuale",
quindi l'automatico riprende da solo `IDLE_TIMEOUT_MANUALE` secondi dopo
l'ultima interazione, che sia stato un testo o uno spegnimento manuale.

## Formato dati

- `messaggi.jsonl` (Pi, invariato) — una riga JSON per messaggio, stessi
  campi restituiti da `history.php`.
- `mostrati.jsonl` (Mac, nuovo) — stesso formato, append-only, **mai
  cancellato**: è insieme lo stato di dedup e l'archivio di tutto ciò che è
  passato sul muro.

## Gestione errori

- `obexftp` fallisce del tutto (nessuna riga `Sending...done`
  nell'output) → loggato sul Pi, nessun retry immediato; il file resta
  cumulativo e verrà riproposto per intero al prossimo ciclo con invio
  riuscito.
- Riga corrotta/troncata in un file `messaggi*.jsonl` ricevuto sul Mac →
  ignorata con warning, il resto del file viene comunque elaborato (stesso
  comportamento di `fetcher.py`).
- Cartella temporaneamente irraggiungibile o problema di permessi sul Mac
  → loggato, il controllo successivo riprova.

## Testing

- `bridge/tests/test_bluetooth_sender.py` — mocka `subprocess.run`: copre
  successo (nonostante "Disconnecting failed" nell'output) e fallimento
  (nessuna riga "Sending...done").
- `bridge/tests/test_fetcher.py` — aggiornato per verificare che
  `bluetooth_sender.invia_file` venga chiamato solo quando il ciclo ha
  scritto messaggi nuovi, e sia saltato se le variabili d'ambiente non sono
  configurate.
- `walltext` — nuova suite pytest (progetto oggi senza test né git, vedi
  "Fuori scope") per `messaggi_watcher.py`: `trova_file_messaggi`,
  `estrai_nuovi` (dedup e righe corrotte), `elabora_cartella`
  (cancellazione dei file sorgente, aggiornamento di `mostrati.jsonl`).
- End-to-end reale (Pi → Bluetooth → Mac → muro) — manuale, non
  automatizzabile da questa sessione.

## Fuori scope

- Inizializzazione di git per la cartella `walltext` — proposta a parte,
  non blocca questa feature.
- Riconnessione automatica se il pairing Bluetooth si perde: si assume che
  pairing/trust restino validi; un fallimento persistente va diagnosticato
  a mano.
- Interfaccia per riordinare o rimuovere manualmente messaggi già accodati
  sul Mac.
- Persistenza della `coda_auto` in memoria tra un riavvio e l'altro di
  `TextWall.py`: se il processo si riavvia, i messaggi già registrati in
  `mostrati.jsonl` ma non ancora mostrati restano "consumati" e non
  tornano in coda — scelta coerente con "mai due volte lo stesso
  messaggio", stesso principio già adottato per `printing` in
  [2026-09-11-hosting-php-polling-design.md](2026-09-11-hosting-php-polling-design.md).

# walltext/messaggi_watcher.py
import glob
import json
import logging
import os

logger = logging.getLogger(__name__)


def trova_file_messaggi(cartella):
    """Ritorna i path dei file messaggi*.jsonl in cartella, ordinati dal
    piu' vecchio al piu' nuovo (data di modifica)."""
    percorsi = glob.glob(os.path.join(cartella, "messaggi*.jsonl"))
    return sorted(percorsi, key=os.path.getmtime)


def carica_id_mostrati(file_stato):
    """Ritorna l'insieme degli id gia' presenti in file_stato. Righe non
    leggibili come JSON vengono ignorate con un warning, senza bloccare
    la lettura delle righe successive."""
    if not os.path.exists(file_stato):
        return set()

    id_visti = set()
    with open(file_stato, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                id_visti.add(json.loads(riga)["id"])
            except (json.JSONDecodeError, KeyError):
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, file_stato)

    return id_visti


def estrai_nuovi(path, id_gia_mostrati):
    """Ritorna i messaggi di path con id non in id_gia_mostrati, dal piu'
    vecchio al piu' nuovo. Righe non leggibili vengono ignorate con un
    warning."""
    nuovi = []
    with open(path, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                messaggio = json.loads(riga)
            except json.JSONDecodeError:
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, path)
                continue
            if messaggio.get("id") not in id_gia_mostrati:
                nuovi.append(messaggio)

    nuovi.sort(key=lambda m: m["id"])
    return nuovi


def elabora_cartella(cartella, file_stato):
    """Elabora tutti i file messaggi*.jsonl trovati in cartella: estrae i
    messaggi mai visti (rispetto a file_stato), li appende a file_stato e
    cancella il file sorgente (anche se non conteneva nulla di nuovo).
    Ritorna la lista di tutti i messaggi nuovi trovati, in ordine (dal
    file piu' vecchio al piu' nuovo, e dentro ciascun file dal messaggio
    piu' vecchio al piu' nuovo)."""
    percorsi = trova_file_messaggi(cartella)
    if not percorsi:
        return []

    id_gia_mostrati = carica_id_mostrati(file_stato)
    tutti_nuovi = []

    for path in percorsi:
        nuovi = estrai_nuovi(path, id_gia_mostrati)
        if nuovi:
            with open(file_stato, "a", encoding="utf-8") as f:
                for messaggio in nuovi:
                    f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")
            for messaggio in nuovi:
                id_gia_mostrati.add(messaggio["id"])
            tutti_nuovi.extend(nuovi)
        os.remove(path)

    return tutti_nuovi


def prossimo_testo_automatico(coda_auto, ultimo_input_manuale, inizio_messaggio_corrente, ora,
                               idle_timeout_manuale, durata_messaggio_auto):
    """Decide se passare al prossimo messaggio della coda automatica e lo
    rimuove da coda_auto in quel caso; altrimenti ritorna None senza
    modificare la coda.

    Condizioni, tutte necessarie:
    - sono passati almeno idle_timeout_manuale secondi dall'ultimo input
      da tastiera (qualunque esso sia stato: testo, comando, o riga vuota);
    - la coda non e' vuota;
    - non c'e' nulla in mostra (inizio_messaggio_corrente is None) oppure
      il messaggio corrente e' in mostra da almeno durata_messaggio_auto
      secondi.
    """
    if ora - ultimo_input_manuale < idle_timeout_manuale:
        return None
    if not coda_auto:
        return None
    if inizio_messaggio_corrente is not None and (ora - inizio_messaggio_corrente) < durata_messaggio_auto:
        return None
    return coda_auto.popleft()

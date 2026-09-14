# bridge/fetcher.py
import json
import logging
import os
import time

import api_client

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 5
LIMITE_STORICO = 100


def _leggi_id_gia_salvati(output_path):
    """Ritorna l'insieme degli id dei messaggi gia' presenti in
    output_path. Non si basa sull'ultimo id visto: un messaggio puo'
    restare bloccato in 'printing' sull'hosting e venire consegnato solo
    piu' tardi, con un id piu' basso di messaggi gia' salvati (vedi
    hosting/README.md). Le righe non leggibili come JSON (es. una scrittura
    interrotta a meta' da uno spegnimento) vengono ignorate con un
    warning, senza bloccare la lettura delle righe successive."""
    if not os.path.exists(output_path):
        return set()

    id_visti = set()
    with open(output_path, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                id_visti.add(json.loads(riga)["id"])
            except (json.JSONDecodeError, KeyError):
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, output_path)

    return id_visti


def process_one_ciclo(base_url, output_path):
    """Recupera lo storico dall'hosting e appende a output_path (JSON
    Lines) i messaggi non ancora presenti nel file, dal piu' vecchio al
    piu' nuovo. Al primo avvio (nessun file precedente) salva tutti i
    messaggi trovati nella pagina, fino a LIMITE_STORICO."""
    try:
        messaggi = api_client.recupera_storico(base_url, limit=LIMITE_STORICO)
    except Exception:
        logger.exception("Errore durante il recupero dello storico")
        return

    id_gia_salvati = _leggi_id_gia_salvati(output_path)
    nuovi = [m for m in messaggi if m["id"] not in id_gia_salvati]
    nuovi.sort(key=lambda m: m["id"])

    if not nuovi:
        return

    with open(output_path, "a", encoding="utf-8") as f:
        for messaggio in nuovi:
            f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")


def fetcher_loop(base_url, output_path):
    while True:
        try:
            process_one_ciclo(base_url, output_path)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di fetch")
        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    base_url = os.environ["API_BASE_URL"]
    output_path = os.environ.get("OUTPUT_FILE", "messaggi.jsonl")

    fetcher_loop(base_url, output_path)

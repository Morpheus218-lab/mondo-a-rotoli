# bridge/fetcher.py
import json
import logging
import os
import time

import api_client

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 5
LIMITE_STORICO = 100


def _leggi_ultimo_id(output_path):
    """Ritorna l'id dell'ultimo messaggio gia' salvato in output_path
    (l'ultima riga del file), o None se il file non esiste o e' vuoto."""
    if not os.path.exists(output_path):
        return None

    ultima_riga = None
    with open(output_path, "r", encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if riga:
                ultima_riga = riga

    if ultima_riga is None:
        return None

    return json.loads(ultima_riga)["id"]


def process_one_ciclo(base_url, output_path):
    """Recupera lo storico dall'hosting e appende a output_path (JSON
    Lines) i messaggi con id maggiore dell'ultimo gia' salvato, dal piu'
    vecchio al piu' nuovo. Al primo avvio (nessun file precedente) salva
    tutti i messaggi trovati nella pagina, fino a LIMITE_STORICO."""
    try:
        messaggi = api_client.recupera_storico(base_url, limit=LIMITE_STORICO)
    except Exception:
        logger.exception("Errore durante il recupero dello storico")
        return

    ultimo_id = _leggi_ultimo_id(output_path)
    nuovi = [m for m in messaggi if ultimo_id is None or m["id"] > ultimo_id]
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

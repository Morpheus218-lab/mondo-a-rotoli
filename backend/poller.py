# backend/poller.py
import logging
import os
import time

import api_client
import printer as printer_module

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 5


def process_one_ciclo(base_url, api_key, stampante):
    try:
        messaggio = api_client.reclama_messaggio(base_url, api_key)
    except Exception:
        logger.exception("Errore durante il claim del messaggio")
        return

    if messaggio is None:
        return

    riuscito = printer_module.stampa_messaggio(stampante, messaggio["text"])

    if not riuscito:
        logger.error(
            "Stampa fallita per il messaggio %s, resta in stato 'printing' "
            "(richiede sblocco manuale, vedi hosting/README.md)",
            messaggio["id"],
        )
        return

    try:
        confermato = api_client.conferma_messaggio(base_url, api_key, messaggio["id"])
        if not confermato:
            logger.error(
                "Ack rifiutato dal server per il messaggio %s "
                "(gia' confermato o non trovato)",
                messaggio["id"],
            )
    except Exception:
        logger.exception(
            "Errore di rete durante l'ack del messaggio %s; il messaggio resta "
            "in stato 'printing' e non verra' ristampato automaticamente",
            messaggio["id"],
        )


def poller_loop(base_url, api_key, stampante):
    while True:
        try:
            process_one_ciclo(base_url, api_key, stampante)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di polling")
        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    base_url = os.environ["API_BASE_URL"]
    api_key = os.environ["API_KEY"]

    stampante = printer_module.get_printer()
    poller_loop(base_url, api_key, stampante)

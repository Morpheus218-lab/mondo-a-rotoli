import logging
import queue

import db
import printer

logger = logging.getLogger(__name__)


def crea_coda():
    return queue.Queue()


def process_one(conn, stampante, message_id):
    messaggio = db.get_message(conn, message_id)
    if messaggio is None:
        return

    riuscito = printer.stampa_messaggio(stampante, messaggio["text"])
    if riuscito:
        db.mark_delivered(conn, message_id)
    else:
        logger.error("Stampa fallita per il messaggio %s, resta pending", message_id)


def worker_loop(coda, conn, stampante):
    while True:
        message_id = coda.get()
        try:
            process_one(conn, stampante, message_id)
        except Exception:
            logger.exception("Errore inatteso processando il messaggio %s", message_id)
        finally:
            coda.task_done()

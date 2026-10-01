# backend/poller.py
import json
import logging
import os
import time

import api_client
import printer as printer_module

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 5
LIMITE_STORICO = 100


def _leggi_id_gia_visti(stato_path):
    """Ritorna l'insieme degli id gia' presenti in stato_path. Righe non
    leggibili come JSON vengono ignorate con un warning, senza bloccare
    la lettura delle righe successive."""
    if not os.path.exists(stato_path):
        return set()

    id_visti = set()
    with open(stato_path, "r", encoding="utf-8") as f:
        for numero_riga, riga in enumerate(f, start=1):
            riga = riga.strip()
            if not riga:
                continue
            try:
                id_visti.add(json.loads(riga)["id"])
            except (json.JSONDecodeError, KeyError):
                logger.warning("Riga %s di %s non leggibile, ignorata", numero_riga, stato_path)

    return id_visti


def _registra_visto(stato_path, messaggio):
    with open(stato_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")


def process_one_ciclo(base_url, stato_path, stampante):
    """Recupera lo storico e stampa i messaggi mai visti, uno alla volta
    in ordine di id. Al primo avvio (stato_path non esiste ancora) non
    stampa nulla: registra tutto come "visto" per partire da li' in poi.
    Un messaggio viene registrato solo dopo stampa riuscita; se uno
    fallisce, i successivi di questo stesso ciclo non vengono tentati
    (restano "nuovi" e si riprova tutti insieme al ciclo dopo)."""
    try:
        messaggi = api_client.recupera_storico(base_url, limit=LIMITE_STORICO)
    except Exception:
        logger.exception("Errore durante il recupero dello storico")
        return

    primo_avvio = not os.path.exists(stato_path)

    if primo_avvio:
        # Crea il file di stato subito, anche se non c'e' ancora nulla da
        # "battezzare": altrimenti, con uno storico vuoto al primo giro, il
        # primo messaggio mai inviato verrebbe assorbito silenziosamente
        # nella baseline del giro successivo invece di essere stampato.
        open(stato_path, "a", encoding="utf-8").close()
        for messaggio in messaggi:
            _registra_visto(stato_path, messaggio)
        if messaggi:
            logger.info(
                "Primo avvio: %s messaggi gia' presenti segnati come visti senza stamparli",
                len(messaggi),
            )
        return

    id_gia_visti = _leggi_id_gia_visti(stato_path)
    nuovi = [m for m in messaggi if m["id"] not in id_gia_visti]
    nuovi.sort(key=lambda m: m["id"])

    for messaggio in nuovi:
        riuscito = printer_module.stampa_messaggio(stampante, messaggio["text"])
        if not riuscito:
            logger.error(
                "Stampa fallita per il messaggio %s, verra' ritentato al prossimo ciclo",
                messaggio["id"],
            )
            return
        _registra_visto(stato_path, messaggio)


def poller_loop(base_url, stato_path, stampante):
    while True:
        try:
            process_one_ciclo(base_url, stato_path, stampante)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di polling")
        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    printer_id = os.environ.get("PRINTER_ID", "")
    formato = (
        f"%(asctime)s [{printer_id}] %(levelname)s %(name)s: %(message)s"
        if printer_id
        else "%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.basicConfig(level=logging.INFO, format=formato)

    base_url = os.environ["API_BASE_URL"]
    stato_path = os.environ.get("STATO_FILE", "stampati.jsonl")

    stampante = printer_module.get_printer()
    poller_loop(base_url, stato_path, stampante)

# backend/api_client.py
import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDI = 10


def reclama_messaggio(base_url, api_key):
    """Chiama POST /claim.php. Ritorna un dict {"id": ..., "text": ...} se
    c'e' un messaggio da stampare, altrimenti None."""
    risposta = requests.post(
        f"{base_url}/claim.php",
        headers={"X-Api-Key": api_key},
        timeout=TIMEOUT_SECONDI,
    )

    if risposta.status_code == 204:
        return None

    risposta.raise_for_status()
    return risposta.json()


def conferma_messaggio(base_url, api_key, message_id):
    """Chiama POST /ack.php. Ritorna True se il messaggio e' stato
    confermato, False se il server risponde 404 (gia' confermato o
    inesistente)."""
    risposta = requests.post(
        f"{base_url}/ack.php",
        headers={"X-Api-Key": api_key},
        json={"id": message_id},
        timeout=TIMEOUT_SECONDI,
    )

    if risposta.status_code == 404:
        return False

    risposta.raise_for_status()
    return True

# bridge/api_client.py
import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDI = 10


def recupera_storico(base_url, limit=100):
    """Chiama GET /history.php?limit=. Ritorna la lista di messaggi
    consegnati (dict con almeno id, text, created_at), piu' recenti
    prima (stesso ordine della risposta dell'API)."""
    risposta = requests.get(
        f"{base_url}/history.php",
        params={"limit": limit},
        timeout=TIMEOUT_SECONDI,
    )
    risposta.raise_for_status()
    return risposta.json()["messaggi"]

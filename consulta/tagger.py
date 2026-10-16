# consulta/tagger.py
import json
import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT_SECONDI = 30

PROMPT_TEMPLATE = (
    "Genera almeno 2 tag brevi (una o due parole, in italiano, minuscolo, "
    "senza '#') che descrivano il tema del seguente messaggio. "
    'Rispondi SOLO con un oggetto JSON nella forma {{"tags": ["tag1", "tag2"]}}, '
    "senza altro testo.\n\nMessaggio: {testo}"
)


def genera_tag(testo, ollama_host, modello):
    """Chiama Ollama (endpoint /api/generate) e ritorna la lista di tag
    generati per testo (almeno 2, se il modello risponde correttamente).
    Ritorna None se la chiamata fallisce o la risposta non e' un JSON
    valido con una lista di almeno 2 tag non vuoti."""
    try:
        risposta = requests.post(
            f"{ollama_host}/api/generate",
            json={
                "model": modello,
                "prompt": PROMPT_TEMPLATE.format(testo=testo),
                "format": "json",
                "stream": False,
            },
            timeout=TIMEOUT_SECONDI,
        )
        risposta.raise_for_status()
        corpo = json.loads(risposta.json()["response"])
        tag = [t.strip() for t in corpo["tags"] if isinstance(t, str) and t.strip()]
    except Exception:
        logger.exception("Errore durante la generazione dei tag con Ollama")
        return None

    if len(tag) < 2:
        logger.warning("Ollama ha generato meno di 2 tag utilizzabili, scartati")
        return None

    return tag

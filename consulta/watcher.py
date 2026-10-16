# consulta/watcher.py
import json
import logging
import os
import time

import api_client
import consulta_writer
import git_publisher
import tagger

logger = logging.getLogger(__name__)

INTERVALLO_SECONDI = 10
LIMITE_STORICO = 100


def _leggi_id_gia_taggati(stato_path):
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


def _registra_taggato(stato_path, messaggio):
    with open(stato_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(messaggio, ensure_ascii=False) + "\n")


def process_one_ciclo(base_url, stato_path, consulta_path, ollama_host, modello):
    """Recupera lo storico e tagga/scrive in testa a consulta_path i
    messaggi mai visti, uno alla volta in ordine di id crescente (cosi'
    l'ultimo scritto, il piu' recente, resta in cima al file). Al primo
    avvio (stato_path non esiste ancora) elabora anche tutto il backlog
    recuperabile, non solo i messaggi arrivati da questo momento in poi.
    Un messaggio viene registrato come taggato solo dopo la scrittura
    riuscita; se la generazione dei tag fallisce, i successivi di questo
    stesso ciclo non vengono tentati (restano "nuovi" e si riprova tutti
    insieme al ciclo dopo)."""
    try:
        messaggi = api_client.recupera_storico(base_url, limit=LIMITE_STORICO)
    except Exception:
        logger.exception("Errore durante il recupero dello storico")
        return

    id_gia_taggati = _leggi_id_gia_taggati(stato_path)
    nuovi = [m for m in messaggi if m["id"] not in id_gia_taggati]
    nuovi.sort(key=lambda m: m["id"])

    for messaggio in nuovi:
        tag = tagger.genera_tag(messaggio["text"], ollama_host, modello)
        if tag is None:
            logger.error(
                "Generazione tag fallita per il messaggio %s, verra' ritentato al prossimo ciclo",
                messaggio["id"],
            )
            return
        consulta_writer.prepend_entry(consulta_path, tag, messaggio["text"])
        _registra_taggato(stato_path, messaggio)


def _pubblica_se_in_programma(consulta_path, remote_url, clone_dir, branch, ultimo_push, intervallo):
    """Se remote_url e' configurato e sono passati almeno intervallo
    secondi dall'ultimo tentativo, clona/aggiorna clone_dir e pubblica
    consulta_path sul repo remoto. Ritorna il nuovo valore di
    ultimo_push (sempre aggiornato dopo un tentativo, riuscito o no, per
    non ritentare ad ogni ciclo in caso di errore persistente)."""
    if not remote_url:
        return ultimo_push
    if time.time() - ultimo_push < intervallo:
        return ultimo_push

    try:
        git_publisher.assicura_clone(remote_url, clone_dir)
        if git_publisher.pubblica(clone_dir, consulta_path, branch):
            logger.info("Consulta.md pubblicato sul repo remoto")
    except Exception:
        logger.exception("Errore durante la pubblicazione di Consulta.md sul repo remoto")

    return time.time()


def watcher_loop(base_url, stato_path, consulta_path, ollama_host, modello,
                  remote_url=None, clone_dir=None, branch="main", push_intervallo=INTERVALLO_SECONDI):
    ultimo_push = 0
    while True:
        try:
            process_one_ciclo(base_url, stato_path, consulta_path, ollama_host, modello)
        except Exception:
            logger.exception("Errore inatteso nel ciclo di tagging")

        ultimo_push = _pubblica_se_in_programma(
            consulta_path, remote_url, clone_dir, branch, ultimo_push, push_intervallo
        )

        time.sleep(INTERVALLO_SECONDI)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    base_url = os.environ["API_BASE_URL"]
    stato_path = os.environ.get("STATO_FILE", "taggati.jsonl")
    consulta_path = os.environ.get("CONSULTA_FILE", "Consulta.md")
    ollama_host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    modello = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")

    remote_url = os.environ.get("CONSULTA_REMOTE_URL")
    clone_dir = os.environ.get(
        "CONSULTA_REMOTE_CLONE_DIR",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "remote-consulta"),
    )
    branch = os.environ.get("CONSULTA_REMOTE_BRANCH", "main")
    push_intervallo = int(os.environ.get("CONSULTA_REMOTE_PUSH_INTERVALLO_SECONDI", INTERVALLO_SECONDI))

    if not remote_url:
        logger.info("CONSULTA_REMOTE_URL non configurata: pubblicazione su repo remoto disattivata")

    watcher_loop(
        base_url, stato_path, consulta_path, ollama_host, modello,
        remote_url, clone_dir, branch, push_intervallo,
    )

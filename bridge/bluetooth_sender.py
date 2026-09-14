# bridge/bluetooth_sender.py
import logging
import subprocess

logger = logging.getLogger(__name__)


def invia_file(path, indirizzo_mac, canale):
    """Invia path al Mac via OBEX Object Push (obexftp). Ritorna True se
    l'output del comando conferma l'invio (contiene "Sending" e "/done"),
    anche se il comando termina con un errore di disconnessione: e' un
    dettaglio noto di obexftp, il Mac chiude la connessione OBEX subito
    dopo il trasferimento, prima della disconnessione esplicita - il file
    arriva comunque."""
    risultato = subprocess.run(
        ["obexftp", "-b", indirizzo_mac, "-B", str(canale), "-p", str(path)],
        capture_output=True,
        text=True,
    )
    output = (risultato.stdout or "") + (risultato.stderr or "")
    return "Sending" in output and "/done" in output

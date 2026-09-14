# bridge/tests/test_bluetooth_sender.py
import bluetooth_sender


class ProcessoFinto:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_invia_file_ritorna_true_se_lo_stdout_conferma_l_invio(monkeypatch):
    stdout = (
        'Connecting..\\done\n'
        'Sending "messaggi.jsonl".../done\n'
        'Disconnecting..-failed: disconnect\n'
    )
    monkeypatch.setattr(
        bluetooth_sender.subprocess,
        "run",
        lambda *a, **k: ProcessoFinto(stdout=stdout, returncode=1),
    )

    assert bluetooth_sender.invia_file("messaggi.jsonl", "A4:CF:99:61:92:F8", 10) is True


def test_invia_file_ritorna_false_se_manca_la_conferma_di_invio(monkeypatch):
    monkeypatch.setattr(
        bluetooth_sender.subprocess,
        "run",
        lambda *a, **k: ProcessoFinto(stdout="", stderr="connect failed", returncode=1),
    )

    assert bluetooth_sender.invia_file("messaggi.jsonl", "A4:CF:99:61:92:F8", 10) is False


def test_invia_file_passa_indirizzo_canale_e_percorso_al_comando(monkeypatch):
    chiamate = []

    def run_finto(comando, **kwargs):
        chiamate.append(comando)
        return ProcessoFinto(stdout='Sending "x".../done')

    monkeypatch.setattr(bluetooth_sender.subprocess, "run", run_finto)

    bluetooth_sender.invia_file("messaggi.jsonl", "A4:CF:99:61:92:F8", 10)

    assert chiamate[0] == [
        "obexftp", "-b", "A4:CF:99:61:92:F8", "-B", "10", "-p", "messaggi.jsonl",
    ]

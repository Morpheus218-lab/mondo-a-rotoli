# backend/tests/test_api_client.py
import api_client


class RispostaFinta:
    def __init__(self, status_code, corpo=None):
        self.status_code = status_code
        self._corpo = corpo

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_reclama_messaggio_ritorna_none_se_204(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(204))

    risultato = api_client.reclama_messaggio("http://esempio", "chiave")

    assert risultato is None


def test_reclama_messaggio_ritorna_messaggio_se_200(monkeypatch):
    corpo = {"id": 1, "text": "ciao"}
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(200, corpo))

    risultato = api_client.reclama_messaggio("http://esempio", "chiave")

    assert risultato == corpo


def test_reclama_messaggio_passa_la_api_key_nell_header(monkeypatch):
    chiamate = []

    def post_finto(url, headers=None, timeout=None, **kwargs):
        chiamate.append((url, headers))
        return RispostaFinta(204)

    monkeypatch.setattr(api_client.requests, "post", post_finto)

    api_client.reclama_messaggio("http://esempio", "segreta")

    assert chiamate[0][1]["X-Api-Key"] == "segreta"


def test_conferma_messaggio_ritorna_true_se_200(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(200))

    assert api_client.conferma_messaggio("http://esempio", "chiave", 1) is True


def test_conferma_messaggio_ritorna_false_se_404(monkeypatch):
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: RispostaFinta(404))

    assert api_client.conferma_messaggio("http://esempio", "chiave", 1) is False

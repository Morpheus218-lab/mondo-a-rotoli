# bridge/tests/test_api_client.py
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


def test_recupera_storico_ritorna_la_lista_messaggi(monkeypatch):
    messaggi = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]
    monkeypatch.setattr(
        api_client.requests, "get", lambda *a, **k: RispostaFinta(200, {"messaggi": messaggi})
    )

    risultato = api_client.recupera_storico("http://esempio")

    assert risultato == messaggi


def test_recupera_storico_passa_il_limit_nei_parametri(monkeypatch):
    chiamate = []

    def get_finto(url, params=None, timeout=None, **kwargs):
        chiamate.append((url, params))
        return RispostaFinta(200, {"messaggi": []})

    monkeypatch.setattr(api_client.requests, "get", get_finto)

    api_client.recupera_storico("http://esempio", limit=100)

    assert chiamate[0][1]["limit"] == 100

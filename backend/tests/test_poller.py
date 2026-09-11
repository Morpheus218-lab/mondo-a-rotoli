# backend/tests/test_poller.py
import poller


class StampanteFinta:
    def __init__(self, fallisce=False):
        self.fallisce = fallisce
        self.testi_stampati = []

    def set(self, **kwargs):
        pass

    def text(self, testo):
        pass

    def image(self, immagine):
        if self.fallisce:
            raise RuntimeError("USB scollegata")
        self.testi_stampati.append(immagine)


def test_process_one_ciclo_non_fa_nulla_se_nessun_messaggio(monkeypatch):
    monkeypatch.setattr(poller.api_client, "reclama_messaggio", lambda *a, **k: None)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)

    assert stampante.testi_stampati == []


def test_process_one_ciclo_stampa_e_conferma(monkeypatch):
    conferme = []
    monkeypatch.setattr(
        poller.api_client, "reclama_messaggio", lambda *a, **k: {"id": 1, "text": "ciao"}
    )
    monkeypatch.setattr(
        poller.api_client,
        "conferma_messaggio",
        lambda base_url, api_key, message_id: conferme.append(message_id) or True,
    )
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)

    assert len(stampante.testi_stampati) == 1
    assert conferme == [1]


def test_process_one_ciclo_non_conferma_se_la_stampa_fallisce(monkeypatch):
    chiamato = []
    monkeypatch.setattr(
        poller.api_client, "reclama_messaggio", lambda *a, **k: {"id": 1, "text": "ciao"}
    )
    monkeypatch.setattr(
        poller.api_client, "conferma_messaggio", lambda *a, **k: chiamato.append(True)
    )
    stampante = StampanteFinta(fallisce=True)

    poller.process_one_ciclo("http://esempio", "chiave", stampante)

    assert chiamato == []


def test_process_one_ciclo_gestisce_errore_di_rete_durante_il_claim(monkeypatch):
    def claim_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(poller.api_client, "reclama_messaggio", claim_rotto)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)  # non deve sollevare

    assert stampante.testi_stampati == []


def test_process_one_ciclo_gestisce_errore_di_rete_durante_l_ack(monkeypatch):
    monkeypatch.setattr(
        poller.api_client, "reclama_messaggio", lambda *a, **k: {"id": 1, "text": "ciao"}
    )

    def ack_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(poller.api_client, "conferma_messaggio", ack_rotto)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", "chiave", stampante)  # non deve sollevare

    assert len(stampante.testi_stampati) == 1

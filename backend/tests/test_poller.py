# backend/tests/test_poller.py
import json

import poller


class StampanteFinta:
    """Simula la stampante. fallisce_dalla_chiamata, se impostato, fa
    sollevare un'eccezione da quella chiamata a image() in poi (1-based):
    es. fallisce_dalla_chiamata=2 fa fallire la seconda stampa e le
    successive."""

    def __init__(self, fallisce_dalla_chiamata=None):
        self.fallisce_dalla_chiamata = fallisce_dalla_chiamata
        self.chiamate = 0
        self.testi_stampati = []

    def set(self, **kwargs):
        pass

    def text(self, testo):
        pass

    def image(self, immagine):
        self.chiamate += 1
        if self.fallisce_dalla_chiamata is not None and self.chiamate >= self.fallisce_dalla_chiamata:
            raise RuntimeError("USB scollegata")
        self.testi_stampati.append(immagine)


def leggi_id_nel_file(path):
    if not path.exists():
        return set()
    id_trovati = set()
    for riga in path.read_text(encoding="utf-8").splitlines():
        if not riga:
            continue
        try:
            id_trovati.add(json.loads(riga)["id"])
        except (json.JSONDecodeError, KeyError):
            continue
    return id_trovati


def test_primo_avvio_non_stampa_nulla_e_segna_tutto_come_visto(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    storico = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert stampante.testi_stampati == []
    assert leggi_id_nel_file(stato_path) == {1, 2}


def test_dopo_il_primo_avvio_stampa_solo_i_messaggi_nuovi(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(json.dumps({"id": 1, "text": "salve"}) + "\n", encoding="utf-8")
    storico = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 1
    assert leggi_id_nel_file(stato_path) == {1, 2}


def test_non_scrive_nulla_se_non_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + json.dumps({"id": 2, "text": "b"}) + "\n",
        encoding="utf-8",
    )
    storico = [{"id": 2, "text": "b"}, {"id": 1, "text": "a"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert stampante.testi_stampati == []
    assert leggi_id_nel_file(stato_path) == {1, 2}


def test_se_un_messaggio_fallisce_i_successivi_non_vengono_stampati_in_questo_ciclo(
    tmp_path, monkeypatch
):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text("", encoding="utf-8")  # file gia' esistente: non e' il primo avvio
    storico = [{"id": 3, "text": "c"}, {"id": 2, "text": "b"}, {"id": 1, "text": "a"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta(fallisce_dalla_chiamata=2)  # fallisce sul messaggio id=2

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 1  # solo id=1 stampato
    assert leggi_id_nel_file(stato_path) == {1}  # id=2 e id=3 restano "nuovi"


def test_riprende_un_messaggio_arrivato_fuori_ordine(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + json.dumps({"id": 3, "text": "c"}) + "\n",
        encoding="utf-8",
    )
    storico = [
        {"id": 4, "text": "d"},
        {"id": 3, "text": "c"},
        {"id": 2, "text": "b"},
        {"id": 1, "text": "a"},
    ]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 2  # id=2 e id=4
    assert leggi_id_nel_file(stato_path) == {1, 2, 3, 4}


def test_gestisce_errore_di_rete_durante_il_recupero_dello_storico(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"

    def recupero_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(poller.api_client, "recupera_storico", recupero_rotto)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)  # non deve sollevare

    assert stampante.testi_stampati == []
    assert not stato_path.exists()


def test_ignora_una_riga_corrotta_senza_bloccarsi(tmp_path, monkeypatch):
    stato_path = tmp_path / "stampati.jsonl"
    stato_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + "questo non e' json valido\n",
        encoding="utf-8",
    )
    storico = [{"id": 2, "text": "b"}, {"id": 1, "text": "a"}]
    monkeypatch.setattr(poller.api_client, "recupera_storico", lambda *a, **k: storico)
    stampante = StampanteFinta()

    poller.process_one_ciclo("http://esempio", str(stato_path), stampante)

    assert len(stampante.testi_stampati) == 1  # id=2 stampato (id=1 gia' visto, riga corrotta ignorata)
    assert leggi_id_nel_file(stato_path) == {1, 2}

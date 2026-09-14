# bridge/tests/test_fetcher.py
import json

import fetcher


def leggi_righe(path):
    if not path.exists():
        return []
    return [json.loads(riga) for riga in path.read_text(encoding="utf-8").splitlines() if riga]


def test_primo_avvio_salva_tutti_i_messaggi_trovati(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 2, "text": "ciao"}, {"id": 1, "text": "salve"}]  # piu' recente prima
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    fetcher.process_one_ciclo("http://esempio", str(output_path))

    righe = leggi_righe(output_path)
    assert [m["id"] for m in righe] == [1, 2]  # scritti dal piu' vecchio al piu' nuovo


def test_salva_solo_i_messaggi_nuovi_rispetto_al_file(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    output_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + json.dumps({"id": 2, "text": "salve"}) + "\n",
        encoding="utf-8",
    )
    storico = [
        {"id": 4, "text": "d"},
        {"id": 3, "text": "c"},
        {"id": 2, "text": "salve"},
        {"id": 1, "text": "a"},
    ]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    fetcher.process_one_ciclo("http://esempio", str(output_path))

    righe = leggi_righe(output_path)
    assert [m["id"] for m in righe] == [1, 2, 3, 4]


def test_non_scrive_nulla_se_non_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    output_path.write_text(
        json.dumps({"id": 4, "text": "d"}) + "\n" + json.dumps({"id": 5, "text": "e"}) + "\n",
        encoding="utf-8",
    )
    storico = [{"id": 5, "text": "e"}, {"id": 4, "text": "d"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    fetcher.process_one_ciclo("http://esempio", str(output_path))

    righe = leggi_righe(output_path)
    assert [m["id"] for m in righe] == [4, 5]


def test_recupera_un_messaggio_consegnato_fuori_ordine_dopo_essere_rimasto_in_printing(
    tmp_path, monkeypatch
):
    # id=2 mancava (era rimasto bloccato in 'printing' all'ultimo giro) mentre
    # id=1 e id=3 erano gia' stati salvati: la dedup non deve basarsi
    # sull'ultimo id visto, altrimenti id=2 non verrebbe mai piu' recuperato.
    output_path = tmp_path / "messaggi.jsonl"
    output_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + json.dumps({"id": 3, "text": "c"}) + "\n",
        encoding="utf-8",
    )
    storico = [
        {"id": 4, "text": "d"},
        {"id": 3, "text": "c"},
        {"id": 2, "text": "b"},
        {"id": 1, "text": "a"},
    ]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    fetcher.process_one_ciclo("http://esempio", str(output_path))

    righe = leggi_righe(output_path)
    assert [m["id"] for m in righe] == [1, 3, 2, 4]


def test_ignora_una_riga_corrotta_senza_bloccarsi(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    output_path.write_text(
        json.dumps({"id": 1, "text": "a"}) + "\n" + "questo non e' json valido\n",
        encoding="utf-8",
    )
    storico = [{"id": 2, "text": "b"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    fetcher.process_one_ciclo("http://esempio", str(output_path))  # non deve sollevare

    contenuto = output_path.read_text(encoding="utf-8")
    assert json.dumps({"id": 2, "text": "b"}, ensure_ascii=False) in contenuto


def test_gestisce_errore_di_rete_durante_il_recupero(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"

    def recupero_rotto(*a, **k):
        raise RuntimeError("rete assente")

    monkeypatch.setattr(fetcher.api_client, "recupera_storico", recupero_rotto)

    fetcher.process_one_ciclo("http://esempio", str(output_path))  # non deve sollevare

    assert not output_path.exists()


def test_invia_via_bluetooth_quando_configurato_e_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 1, "text": "ciao"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    chiamate = []
    monkeypatch.setattr(
        fetcher.bluetooth_sender,
        "invia_file",
        lambda path, mac, canale: chiamate.append((path, mac, canale)) or True,
    )

    fetcher.process_one_ciclo(
        "http://esempio", str(output_path), indirizzo_mac="A4:CF:99:61:92:F8", canale=10
    )

    assert chiamate == [(str(output_path), "A4:CF:99:61:92:F8", 10)]


def test_non_invia_via_bluetooth_se_non_configurato(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 1, "text": "ciao"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def invia_file_non_atteso(*a, **k):
        raise AssertionError("invia_file non doveva essere chiamato")

    monkeypatch.setattr(fetcher.bluetooth_sender, "invia_file", invia_file_non_atteso)

    fetcher.process_one_ciclo("http://esempio", str(output_path))  # nessun mac/canale


def test_non_invia_via_bluetooth_se_non_ci_sono_messaggi_nuovi(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    output_path.write_text(json.dumps({"id": 1, "text": "a"}) + "\n", encoding="utf-8")
    storico = [{"id": 1, "text": "a"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def invia_file_non_atteso(*a, **k):
        raise AssertionError("invia_file non doveva essere chiamato")

    monkeypatch.setattr(fetcher.bluetooth_sender, "invia_file", invia_file_non_atteso)

    fetcher.process_one_ciclo(
        "http://esempio", str(output_path), indirizzo_mac="A4:CF:99:61:92:F8", canale=10
    )


def test_gestisce_errore_durante_invio_bluetooth_senza_sollevare(tmp_path, monkeypatch):
    output_path = tmp_path / "messaggi.jsonl"
    storico = [{"id": 1, "text": "ciao"}]
    monkeypatch.setattr(fetcher.api_client, "recupera_storico", lambda *a, **k: storico)

    def invia_file_rotto(*a, **k):
        raise RuntimeError("bluetooth non disponibile")

    monkeypatch.setattr(fetcher.bluetooth_sender, "invia_file", invia_file_rotto)

    fetcher.process_one_ciclo(  # non deve sollevare
        "http://esempio", str(output_path), indirizzo_mac="A4:CF:99:61:92:F8", canale=10
    )

    contenuto = output_path.read_text(encoding="utf-8")
    assert json.dumps({"id": 1, "text": "ciao"}, ensure_ascii=False) in contenuto

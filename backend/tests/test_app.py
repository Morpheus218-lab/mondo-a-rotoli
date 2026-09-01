import queue

import pytest

import app as app_module
import db


@pytest.fixture
def client(tmp_path):
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    coda = queue.Queue()
    flask_app = app_module.create_app(conn, coda)
    flask_app.config["TESTING"] = True
    return flask_app.test_client(), conn, coda


def test_post_message_salva_pending_e_accoda(client):
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": "ciao mondo"})

    assert risposta.status_code == 202
    corpo = risposta.get_json()
    assert corpo["ok"] is True
    assert isinstance(corpo["id"], int)

    riga = db.get_message(conn, corpo["id"])
    assert riga["text"] == "ciao mondo"
    assert riga["status"] == "pending"
    assert coda.get_nowait() == corpo["id"]


def test_post_message_senza_testo_ritorna_400(client):
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": "   "})

    assert risposta.status_code == 400
    assert coda.empty()


def test_post_message_corpo_non_dict_ritorna_400(client):
    """Test that a JSON body that isn't a dict (e.g., a bare array) returns 400, not 500."""
    test_client, conn, coda = client

    risposta = test_client.post("/message", json=[1, 2, 3])

    assert risposta.status_code == 400
    assert coda.empty()


def test_post_message_text_non_string_ritorna_400(client):
    """Test that a non-string text value (e.g., integer) returns 400, not 500."""
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": 123})

    assert risposta.status_code == 400
    assert coda.empty()


def test_get_history_ritorna_solo_delivered(client):
    test_client, conn, coda = client
    id1, _ = db.insert_message(conn, "uno")
    db.mark_delivered(conn, id1)
    db.insert_message(conn, "due")  # resta pending, non deve comparire

    risposta = test_client.get("/message/history")

    assert risposta.status_code == 200
    messaggi = risposta.get_json()["messaggi"]
    assert len(messaggi) == 1
    assert messaggi[0]["text"] == "uno"


def test_get_history_rispetta_limit_e_offset(client):
    test_client, conn, coda = client
    for testo in ["uno", "due", "tre"]:
        message_id, _ = db.insert_message(conn, testo)
        db.mark_delivered(conn, message_id)

    risposta = test_client.get("/message/history?limit=1&offset=1")

    messaggi = risposta.get_json()["messaggi"]
    assert [m["text"] for m in messaggi] == ["due"]


def test_post_message_testo_oltre_1000_caratteri_ritorna_400(client):
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": "a" * 1500})

    assert risposta.status_code == 400
    assert coda.empty()


def test_post_message_testo_tra_100_e_150_caratteri_viene_accettato(client):
    """Comportamento esistente invariato: un messaggio piu' lungo del limite
    di stampa (100 caratteri, printer.LIMITE_CARATTERI) ma sotto il tetto
    di storage (1000) deve continuare a essere accettato e salvato — verra'
    stampato come avviso "troppo lungo" da printer.py, non rifiutato qui."""
    test_client, conn, coda = client

    risposta = test_client.post("/message", json={"text": "a" * 120})

    assert risposta.status_code == 202
    corpo = risposta.get_json()
    riga = db.get_message(conn, corpo["id"])
    assert riga is not None
    assert len(riga["text"]) == 120


def test_get_history_limit_negativo_e_limitato_a_100(client):
    """limit=-1 non deve piu' significare "nessun limite" (comportamento
    nativo di SQLite per LIMIT negativo): va vincolato nell'intervallo
    [1, 100], quindi al minimo 1, mai l'intera tabella."""
    test_client, conn, coda = client
    for i in range(5):
        message_id, _ = db.insert_message(conn, f"msg-{i}")
        db.mark_delivered(conn, message_id)

    risposta = test_client.get("/message/history?limit=-1")

    assert risposta.status_code == 200
    messaggi = risposta.get_json()["messaggi"]
    assert len(messaggi) <= 100


def test_get_history_limit_grande_e_limitato_a_100(client):
    test_client, conn, coda = client
    for i in range(150):
        message_id, _ = db.insert_message(conn, f"msg-{i}")
        db.mark_delivered(conn, message_id)

    risposta = test_client.get("/message/history?limit=99999")

    assert risposta.status_code == 200
    messaggi = risposta.get_json()["messaggi"]
    assert len(messaggi) == 100


def test_get_history_offset_negativo_e_trattato_come_zero(client):
    test_client, conn, coda = client
    for testo in ["uno", "due", "tre"]:
        message_id, _ = db.insert_message(conn, testo)
        db.mark_delivered(conn, message_id)

    risposta_negativo = test_client.get("/message/history?offset=-5")
    risposta_zero = test_client.get("/message/history?offset=0")

    assert risposta_negativo.status_code == 200
    assert risposta_negativo.get_json()["messaggi"] == risposta_zero.get_json()["messaggi"]

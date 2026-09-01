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

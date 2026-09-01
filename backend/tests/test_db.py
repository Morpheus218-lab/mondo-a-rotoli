import threading

import db


def _fresh_conn(tmp_path):
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    return conn


def test_insert_message_sets_pending_status(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, created_at = db.insert_message(conn, "ciao")
    row = conn.execute("SELECT * FROM messaggi WHERE id = ?", (message_id,)).fetchone()
    assert row["text"] == "ciao"
    assert row["status"] == "pending"
    assert row["created_at"] == created_at


def test_mark_delivered_updates_status(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    db.mark_delivered(conn, message_id)
    row = conn.execute("SELECT status FROM messaggi WHERE id = ?", (message_id,)).fetchone()
    assert row["status"] == "delivered"


def test_get_pending_ids_returns_only_pending_in_order(tmp_path):
    conn = _fresh_conn(tmp_path)
    id1, _ = db.insert_message(conn, "uno")
    id2, _ = db.insert_message(conn, "due")
    db.mark_delivered(conn, id1)
    id3, _ = db.insert_message(conn, "tre")
    assert db.get_pending_ids(conn) == [id2, id3]


def test_get_message_returns_dict_or_none(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    assert db.get_message(conn, message_id)["text"] == "ciao"
    assert db.get_message(conn, 9999) is None


def test_get_history_returns_delivered_desc_with_pagination(tmp_path):
    conn = _fresh_conn(tmp_path)
    for testo in ["uno", "due", "tre"]:
        message_id, _ = db.insert_message(conn, testo)
        db.mark_delivered(conn, message_id)

    pagina1 = db.get_history(conn, limit=2, offset=0)
    assert [r["text"] for r in pagina1] == ["tre", "due"]

    pagina2 = db.get_history(conn, limit=2, offset=2)
    assert [r["text"] for r in pagina2] == ["uno"]


def test_insert_message_concorrenti_non_producono_id_duplicati(tmp_path):
    """Regression test per il bug della connessione sqlite3 condivisa senza
    lock tra thread: senza il lock in db.py, cursor.lastrowid puo'
    restituire lo stesso id per insert concorrenti (sqlite3_last_insert_rowid
    e' globale alla connessione, non thread-local), causando doppie stampe
    e messaggi persi."""
    conn = _fresh_conn(tmp_path)
    n_thread = 8
    inserti_per_thread = 20
    ids_lock = threading.Lock()
    ids_raccolti = []
    errori = []

    def worker(indice_thread):
        try:
            for i in range(inserti_per_thread):
                message_id, _ = db.insert_message(conn, f"thread-{indice_thread}-msg-{i}")
                with ids_lock:
                    ids_raccolti.append(message_id)
        except Exception as exc:  # pragma: no cover - solo per diagnosi in caso di fallimento
            errori.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_thread)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errori == []

    totale_attesi = n_thread * inserti_per_thread
    assert len(ids_raccolti) == totale_attesi
    assert len(set(ids_raccolti)) == totale_attesi, "sono stati rilevati id duplicati"

    riga_conteggio = conn.execute("SELECT COUNT(*) AS n FROM messaggi").fetchone()
    assert riga_conteggio["n"] == totale_attesi

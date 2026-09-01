import queue

import db
import worker


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


def _fresh_conn(tmp_path):
    conn = db.connect(str(tmp_path / "test.db"))
    db.init_db(conn)
    return conn


def test_process_one_stampa_e_marca_delivered(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    stampante = StampanteFinta()

    worker.process_one(conn, stampante, message_id)

    assert len(stampante.testi_stampati) == 1
    assert db.get_message(conn, message_id)["status"] == "delivered"


def test_process_one_lascia_pending_se_la_stampa_fallisce(tmp_path):
    conn = _fresh_conn(tmp_path)
    message_id, _ = db.insert_message(conn, "ciao")
    stampante = StampanteFinta(fallisce=True)

    worker.process_one(conn, stampante, message_id)

    assert db.get_message(conn, message_id)["status"] == "pending"


def test_process_one_ignora_id_inesistente(tmp_path):
    conn = _fresh_conn(tmp_path)
    stampante = StampanteFinta()

    worker.process_one(conn, stampante, 9999)  # non deve sollevare eccezioni

    assert stampante.testi_stampati == []


def test_process_one_rispetta_ordine_fifo_della_coda(tmp_path):
    conn = _fresh_conn(tmp_path)
    id1, _ = db.insert_message(conn, "uno")
    id2, _ = db.insert_message(conn, "due")

    coda = queue.Queue()
    coda.put(id1)
    coda.put(id2)

    stampante = StampanteFinta()
    worker.process_one(conn, stampante, coda.get())
    worker.process_one(conn, stampante, coda.get())

    assert db.get_message(conn, id1)["status"] == "delivered"
    assert db.get_message(conn, id2)["status"] == "delivered"

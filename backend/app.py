import logging
import os
import threading

from flask import Flask, jsonify, request
from flask_cors import CORS

import db
import printer as printer_module
import worker

DEFAULT_LIMIT = 10
MAX_TEXT_LENGTH = 1000


def create_app(conn, coda):
    app = Flask(__name__)
    CORS(app)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    @app.post("/message")
    def message():
        corpo = request.get_json(silent=True) or {}

        # Validate that corpo is a dict
        if not isinstance(corpo, dict):
            return jsonify({"error": 'Il campo "text" è obbligatorio'}), 400

        # Validate that text is a string
        text_value = corpo.get("text")
        if not isinstance(text_value, str):
            return jsonify({"error": 'Il campo "text" è obbligatorio'}), 400

        testo = text_value.strip()

        if not testo:
            return jsonify({"error": 'Il campo "text" è obbligatorio'}), 400

        if len(testo) > MAX_TEXT_LENGTH:
            return (
                jsonify(
                    {"error": f'Il campo "text" supera il limite di {MAX_TEXT_LENGTH} caratteri'}
                ),
                400,
            )

        message_id, created_at = db.insert_message(conn, testo)
        coda.put(message_id)

        return jsonify({"ok": True, "id": message_id, "createdAt": created_at}), 202

    @app.get("/message/history")
    def history():
        limit = request.args.get("limit", default=DEFAULT_LIMIT, type=int)
        offset = request.args.get("offset", default=0, type=int)
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        messaggi = db.get_history(conn, limit, offset)
        return jsonify({"messaggi": messaggi})

    return app


DB_PATH = os.path.join(os.path.dirname(__file__), "installazione.db")


def _recupera_pending(conn, coda):
    for message_id in db.get_pending_ids(conn):
        coda.put(message_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    conn = db.connect(DB_PATH)
    db.init_db(conn)

    coda = worker.crea_coda()
    _recupera_pending(conn, coda)

    stampante = printer_module.get_printer()
    thread_stampa = threading.Thread(
        target=worker.worker_loop, args=(coda, conn, stampante), daemon=True
    )
    thread_stampa.start()

    app = create_app(conn, coda)
    app.run(host="0.0.0.0", port=5000)

from flask import Flask, jsonify, request
from flask_cors import CORS

import db

DEFAULT_LIMIT = 10


def create_app(conn, coda):
    app = Flask(__name__)
    CORS(app)

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

        message_id, created_at = db.insert_message(conn, testo)
        coda.put(message_id)

        return jsonify({"ok": True, "id": message_id, "createdAt": created_at}), 202

    @app.get("/message/history")
    def history():
        limit = request.args.get("limit", default=DEFAULT_LIMIT, type=int)
        offset = request.args.get("offset", default=0, type=int)
        messaggi = db.get_history(conn, limit, offset)
        return jsonify({"messaggi": messaggi})

    return app

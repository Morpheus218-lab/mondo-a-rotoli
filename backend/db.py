import os
import sqlite3
import threading
from datetime import datetime, timezone

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# La connessione sqlite3 e' condivisa tra il thread di Flask e il thread
# worker (check_same_thread=False). sqlite3.Connection non e' sicura per
# l'uso concorrente da piu' thread senza serializzazione esterna: in
# particolare cursor.lastrowid si basa su sqlite3_last_insert_rowid(), che
# e' globale alla connessione (non thread-local), quindi insert concorrenti
# possono restituire lo stesso id. Questo lock serializza ogni operazione
# pubblica su questo modulo.
_lock = threading.RLock()


def connect(db_path):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn):
    with _lock:
        with open(SCHEMA_PATH) as f:
            conn.executescript(f.read())
        conn.commit()


def insert_message(conn, text):
    with _lock:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = conn.execute(
            "INSERT INTO messaggi (text, created_at, status) VALUES (?, ?, ?)",
            (text, created_at, "pending"),
        )
        conn.commit()
        return cursor.lastrowid, created_at


def mark_delivered(conn, message_id):
    with _lock:
        conn.execute("UPDATE messaggi SET status = ? WHERE id = ?", ("delivered", message_id))
        conn.commit()


def get_pending_ids(conn):
    with _lock:
        rows = conn.execute(
            "SELECT id FROM messaggi WHERE status = 'pending' ORDER BY id ASC"
        ).fetchall()
        return [row["id"] for row in rows]


def get_message(conn, message_id):
    with _lock:
        row = conn.execute("SELECT * FROM messaggi WHERE id = ?", (message_id,)).fetchone()
        return dict(row) if row else None


def get_history(conn, limit, offset):
    with _lock:
        rows = conn.execute(
            "SELECT * FROM messaggi WHERE status = 'delivered' ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]

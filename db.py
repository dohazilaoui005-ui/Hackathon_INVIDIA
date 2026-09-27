"""
Lightweight SQLite persistence. Good enough for a prototype/demo deployment;
swap DATABASE_PATH for a managed Postgres URL + a different driver later
without changing the call sites in app.py.
"""
import sqlite3
import os
import json
import logging
import datetime

logger = logging.getLogger("case_analyzer.db")

DB_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "data", "cases.db"),
)


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_db():
    try:
        conn = get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cases (
                id TEXT PRIMARY KEY,
                input_text TEXT,
                profile_json TEXT,
                rag_result_json TEXT,
                final_response_json TEXT,
                created_at TEXT
            )
            """
        )
        conn.commit()
        conn.close()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"DB init failed: {e}")


def save_case(case_id: str, input_text: str, user_profile: dict, rag_result: dict, final_response: dict) -> bool:
    try:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO cases "
            "(id, input_text, profile_json, rag_result_json, final_response_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                case_id,
                input_text,
                json.dumps(user_profile),
                json.dumps(rag_result),
                json.dumps(final_response),
                datetime.datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB save failed: {e}")
        return False


def get_case(case_id: str):
    try:
        conn = get_conn()
        cur = conn.execute(
            "SELECT id, input_text, profile_json, rag_result_json, final_response_json, created_at "
            "FROM cases WHERE id = ?",
            (case_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0],
            "input_text": row[1],
            "user_profile": json.loads(row[2]),
            "rag_result": json.loads(row[3]),
            "final_response": json.loads(row[4]),
            "created_at": row[5],
        }
    except Exception as e:
        logger.error(f"DB read failed: {e}")
        return None

import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional


class Database:
    def __init__(self, database_url: str):
        # Parse sqlite URL: sqlite:////data/app.db -> /data/app.db
        if database_url.startswith("sqlite:////"):
            self.db_path = "/" + database_url[len("sqlite:////"):]
        elif database_url.startswith("sqlite:///"):
            self.db_path = database_url[len("sqlite:///"):]
        else:
            self.db_path = database_url

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id  TEXT    NOT NULL,
                    role        TEXT    NOT NULL,
                    content     TEXT    NOT NULL,
                    metadata    TEXT,
                    created_at  TEXT    NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session ON messages(session_id)"
            )
            conn.commit()

    def check_health(self):
        with self._get_conn() as conn:
            conn.execute("SELECT 1")

    def session_exists(self, session_id: str) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM messages WHERE session_id = ? LIMIT 1",
                (session_id,),
            ).fetchone()
            return row is not None

    def get_messages(self, session_id: str) -> List[Dict]:
        """Return plain role/content list for LLM history."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def get_messages_with_metadata(self, session_id: str) -> List[Dict]:
        """Return full history including metadata for the /sessions endpoint."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT role, content, metadata FROM messages WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
        result = []
        for r in rows:
            msg: Dict = {"role": r["role"], "content": r["content"]}
            if r["metadata"]:
                try:
                    msg["metadata"] = json.loads(r["metadata"])
                except Exception:
                    pass
            result.append(msg)
        return result

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict] = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        meta_str = json.dumps(metadata) if metadata else None
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, metadata, created_at) VALUES (?,?,?,?,?)",
                (session_id, role, content, meta_str, now),
            )
            conn.commit()

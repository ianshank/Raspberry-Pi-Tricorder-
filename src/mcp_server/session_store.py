"""Chat session persistence layer.

Provides a ``SessionStore`` protocol with two implementations:

* ``InMemorySessionStore`` -- dict-backed store for testing.
* ``SqliteSessionStore``   -- WAL-mode SQLite store that survives restarts.

Use the ``create_session_store`` factory to pick the right backend at
startup based on a *db_path* config value.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SessionStore(Protocol):
    """Minimal interface for chat-session persistence."""

    def create_session(self, operator_id: str = "") -> str:
        """Create a new session and return its ID."""
        ...

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Return all messages for *session_id*, or empty list if not found."""
        ...

    def append_message(self, session_id: str, message: Dict[str, Any]) -> None:
        """Append a message to the session's message list."""
        ...

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return metadata dict for *session_id*, or ``None`` if not found."""
        ...

    def cleanup_expired(self, ttl_seconds: int) -> int:
        """Delete sessions whose *updated_at* is older than *ttl_seconds* ago.

        Returns the number of deleted sessions.
        """
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (testing)
# ---------------------------------------------------------------------------

class InMemorySessionStore:
    """Dict-backed session store for unit tests and development."""

    def __init__(self, default_ttl_s: int = 3600) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._default_ttl_s = default_ttl_s
        logger.info("Session store initialised: in-memory (ttl=%ds)", default_ttl_s)

    # -- protocol methods ---------------------------------------------------

    def create_session(self, operator_id: str = "") -> str:
        session_id = f"sess-{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        self._sessions[session_id] = {
            "session_id": session_id,
            "operator_id": operator_id,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        return session_id

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if session is None:
            return []
        return list(session["messages"])

    def append_message(self, session_id: str, message: Dict[str, Any]) -> None:
        session = self._sessions.get(session_id)
        if session is None:
            logger.warning("append_message: session %s not found", session_id)
            return
        session["messages"].append(message)
        session["updated_at"] = datetime.now(timezone.utc).isoformat()

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return {
            "session_id": session["session_id"],
            "operator_id": session["operator_id"],
            "message_count": len(session["messages"]),
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
        }

    def cleanup_expired(self, ttl_seconds: int) -> int:
        from datetime import timedelta

        cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        cutoff = cutoff_dt.isoformat()

        expired = [
            sid for sid, s in self._sessions.items()
            if s["updated_at"] < cutoff
        ]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.debug("Cleaned up %d expired sessions (ttl=%ds)", len(expired), ttl_seconds)
        return len(expired)


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS chat_sessions (
    session_id  TEXT PRIMARY KEY,
    operator_id TEXT NOT NULL DEFAULT '',
    messages    TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at "
    "ON chat_sessions(updated_at);"
)


class SqliteSessionStore:
    """WAL-mode SQLite session store — survives service restarts."""

    def __init__(self, db_path: str, default_ttl_s: int = 3600) -> None:
        self._db_path = db_path
        self._default_ttl_s = default_ttl_s
        self._write_lock = threading.Lock()
        self._ensure_parent_dir()
        self._ensure_schema()
        logger.info("Session store initialised: db=%s, ttl=%ds", db_path, default_ttl_s)

    # -- protocol methods ---------------------------------------------------

    def create_session(self, operator_id: str = "") -> str:
        session_id = f"sess-{uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat()
        with self._write_lock:
            with self._connection() as conn:
                conn.execute(
                    "INSERT INTO chat_sessions "
                    "(session_id, operator_id, messages, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (session_id, operator_id, "[]", now, now),
                )
                conn.commit()
        return session_id

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT messages FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return []
        return json.loads(row[0])

    def append_message(self, session_id: str, message: Dict[str, Any]) -> None:
        with self._write_lock:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT messages FROM chat_sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if row is None:
                    logger.warning("append_message: session %s not found", session_id)
                    return
                messages: list = json.loads(row[0])
                messages.append(message)
                now = datetime.now(timezone.utc).isoformat()
                conn.execute(
                    "UPDATE chat_sessions SET messages = ?, updated_at = ? "
                    "WHERE session_id = ?",
                    (json.dumps(messages), now, session_id),
                )
                conn.commit()

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT session_id, operator_id, messages, created_at, updated_at "
                "FROM chat_sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "session_id": row[0],
            "operator_id": row[1],
            "message_count": len(json.loads(row[2])),
            "created_at": row[3],
            "updated_at": row[4],
        }

    def cleanup_expired(self, ttl_seconds: int) -> int:
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)).isoformat()
        with self._write_lock:
            with self._connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM chat_sessions WHERE updated_at < ?",
                    (cutoff,),
                )
                conn.commit()
                deleted = cursor.rowcount
        if deleted:
            logger.debug("Cleaned up %d expired sessions (ttl=%ds)", deleted, ttl_seconds)
        return deleted

    # -- internals ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_parent_dir(self) -> None:
        parent = Path(self._db_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    def _ensure_schema(self) -> None:
        with self._connection() as conn:
            conn.executescript(_SCHEMA_SQL + _INDEX_SQL)
            conn.commit()
        logger.debug("Session store schema verified")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_session_store(
    db_path: Optional[str] = None,
    default_ttl_s: int = 3600,
) -> SessionStore:
    """Create the appropriate session store backend.

    Returns ``SqliteSessionStore`` when *db_path* is a non-empty string,
    otherwise falls back to ``InMemorySessionStore``.
    """
    if db_path:
        return SqliteSessionStore(db_path=db_path, default_ttl_s=default_ttl_s)
    return InMemorySessionStore(default_ttl_s=default_ttl_s)

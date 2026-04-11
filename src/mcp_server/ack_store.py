"""Anomaly acknowledgment persistence layer.

Provides an ``AckStore`` protocol with two implementations:

* ``InMemoryAckStore`` – dict-backed store (backwards-compatible default).
* ``SqliteAckStore``  – WAL-mode SQLite store that survives restarts.

Use the ``create_ack_store`` factory to pick the right backend at
startup based on the ``anomaly_ack_db_path`` config value.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from utils.constants import SQLITE_BUSY_TIMEOUT_MS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class AckStore(Protocol):
    """Minimal interface for anomaly-acknowledgment persistence."""

    def upsert(self, anomaly_id: str, record: Dict[str, Any]) -> None:
        """Insert or update an acknowledgment record."""
        ...

    def get(self, anomaly_id: str) -> Optional[Dict[str, Any]]:
        """Return a single ACK record, or ``None`` if not found."""
        ...

    def list_acks(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Return paginated ACK records, newest first."""
        ...

    def count(self, filters: Optional[Dict[str, str]] = None) -> int:
        """Return total number of stored ACK records."""
        ...

    def evict(self, max_records: int) -> int:
        """Delete the oldest records beyond *max_records*. Return count deleted."""
        ...


# ---------------------------------------------------------------------------
# In-memory implementation (backwards compat)
# ---------------------------------------------------------------------------

class InMemoryAckStore:
    """Dict-backed ACK store — matches the original server.py behaviour."""

    def __init__(self, max_records: int = 500) -> None:
        self._records: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []
        self._max_records = max_records
        logger.info("ACK store initialised: in-memory (max_records=%d)", max_records)

    # -- protocol methods ---------------------------------------------------

    def upsert(self, anomaly_id: str, record: Dict[str, Any]) -> None:
        if anomaly_id not in self._records:
            self._order.append(anomaly_id)
        self._records[anomaly_id] = record
        self._maybe_evict()

    def get(self, anomaly_id: str) -> Optional[Dict[str, Any]]:
        return self._records.get(anomaly_id)

    def list_acks(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        items = list(reversed(self._order))
        if filters:
            items = [
                aid for aid in items
                if self._matches_filters(self._records[aid], filters)
            ]
        return [self._records[aid] for aid in items[offset: offset + limit]]

    def count(self, filters: Optional[Dict[str, str]] = None) -> int:
        if not filters:
            return len(self._records)
        return sum(
            1 for r in self._records.values()
            if self._matches_filters(r, filters)
        )

    def evict(self, max_records: int) -> int:
        deleted = 0
        while len(self._order) > max_records:
            oldest = self._order.pop(0)
            self._records.pop(oldest, None)
            deleted += 1
        return deleted

    # -- internals ----------------------------------------------------------

    def _maybe_evict(self) -> None:
        evicted = self.evict(self._max_records)
        if evicted:
            logger.debug("Evicted %d old ACK records (limit=%d)", evicted, self._max_records)

    @staticmethod
    def _matches_filters(record: Dict[str, Any], filters: Dict[str, str]) -> bool:
        for key, value in filters.items():
            record_value = record.get(key, "")
            if key in ("date_from", "date_to"):
                ack_ts = record.get("acknowledged_at", "")
                if key == "date_from" and ack_ts < value:
                    return False
                if key == "date_to" and ack_ts > value:
                    return False
            elif str(record_value) != value:
                return False
        return True


# ---------------------------------------------------------------------------
# SQLite implementation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS anomaly_acks (
    anomaly_id      TEXT PRIMARY KEY,
    acknowledged_at TEXT NOT NULL,
    acknowledged_by TEXT NOT NULL DEFAULT 'ui',
    note            TEXT NOT NULL DEFAULT '',
    operator_source TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
"""

_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_acks_acknowledged_at "
    "ON anomaly_acks(acknowledged_at);"
)

_COLUMNS = (
    "anomaly_id", "acknowledged_at", "acknowledged_by",
    "note", "operator_source", "created_at",
)


class SqliteAckStore:
    """WAL-mode SQLite ACK store — survives service restarts."""

    def __init__(self, db_path: str, max_records: int = 500) -> None:
        self._db_path = db_path
        self._max_records = max_records
        self._ensure_parent_dir()
        self._ensure_schema()
        logger.info("ACK store initialised: db=%s, max_records=%d", db_path, max_records)

    # -- protocol methods ---------------------------------------------------

    def upsert(self, anomaly_id: str, record: Dict[str, Any]) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO anomaly_acks "
                "(anomaly_id, acknowledged_at, acknowledged_by, note, operator_source) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    anomaly_id,
                    record.get("acknowledged_at", datetime.now(timezone.utc).isoformat()),
                    record.get("acknowledged_by", "ui"),
                    record.get("note", ""),
                    record.get("operator_source", ""),
                ),
            )
            conn.commit()
        self._maybe_evict()

    def get(self, anomaly_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM anomaly_acks WHERE anomaly_id = ?",
                (anomaly_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_acks(
        self,
        limit: int = 50,
        offset: int = 0,
        filters: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM anomaly_acks"
        params: List[Any] = []
        clauses = self._build_where_clauses(filters, params)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY acknowledged_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self, filters: Optional[Dict[str, str]] = None) -> int:
        query = "SELECT COUNT(*) FROM anomaly_acks"
        params: List[Any] = []
        clauses = self._build_where_clauses(filters, params)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        with self._connection() as conn:
            row = conn.execute(query, params).fetchone()
        return int(row[0]) if row else 0

    def evict(self, max_records: int) -> int:
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM anomaly_acks WHERE anomaly_id NOT IN "
                "(SELECT anomaly_id FROM anomaly_acks "
                "ORDER BY created_at DESC LIMIT ?)",
                (max_records,),
            )
            conn.commit()
            return cursor.rowcount

    # -- internals ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
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
        logger.debug("ACK store schema verified")

    def _maybe_evict(self) -> None:
        evicted = self.evict(self._max_records)
        if evicted:
            logger.debug("Evicted %d old ACK records (limit=%d)", evicted, self._max_records)

    @staticmethod
    def _row_to_dict(row: tuple) -> Dict[str, Any]:  # type: ignore[type-arg]
        return dict(zip(_COLUMNS, row))

    @staticmethod
    def _build_where_clauses(
        filters: Optional[Dict[str, str]],
        params: List[Any],
    ) -> List[str]:
        clauses: List[str] = []
        if not filters:
            return clauses
        if "acknowledged_by" in filters:
            clauses.append("acknowledged_by = ?")
            params.append(filters["acknowledged_by"])
        if "date_from" in filters:
            clauses.append("acknowledged_at >= ?")
            params.append(filters["date_from"])
        if "date_to" in filters:
            clauses.append("acknowledged_at <= ?")
            params.append(filters["date_to"])
        if "operator_source" in filters:
            clauses.append("operator_source = ?")
            params.append(filters["operator_source"])
        return clauses


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_ack_store(
    db_path: Optional[str] = None,
    max_records: int = 500,
) -> AckStore:
    """Create the appropriate ACK store backend.

    Returns ``SqliteAckStore`` when *db_path* is a non-empty string,
    otherwise falls back to ``InMemoryAckStore``.
    """
    if db_path:
        return SqliteAckStore(db_path=db_path, max_records=max_records)
    return InMemoryAckStore(max_records=max_records)

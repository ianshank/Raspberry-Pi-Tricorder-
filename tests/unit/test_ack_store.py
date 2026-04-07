"""Tests for mcp_server.ack_store — InMemory and SQLite backends."""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone

from mcp_server.ack_store import (
    AckStore,
    InMemoryAckStore,
    SqliteAckStore,
    create_ack_store,
)


def _make_record(
    anomaly_id: str = "a-001",
    acknowledged_by: str = "ui",
    note: str = "",
    operator_source: str = "",
) -> dict:
    return {
        "anomaly_id": anomaly_id,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "acknowledged_by": acknowledged_by,
        "note": note,
        "operator_source": operator_source,
    }


# ── InMemoryAckStore ────────────────────────────────────────────────────────


class TestInMemoryAckStore:
    def test_upsert_and_get(self) -> None:
        store = InMemoryAckStore(max_records=100)
        rec = _make_record("a-001")
        store.upsert("a-001", rec)
        assert store.get("a-001") == rec

    def test_get_returns_none_for_unknown(self) -> None:
        store = InMemoryAckStore()
        assert store.get("nope") is None

    def test_upsert_updates_existing(self) -> None:
        store = InMemoryAckStore()
        store.upsert("a-001", _make_record("a-001", note="first"))
        store.upsert("a-001", _make_record("a-001", note="second"))
        record = store.get("a-001")
        assert record is not None
        assert record["note"] == "second"
        assert store.count() == 1

    def test_count(self) -> None:
        store = InMemoryAckStore()
        assert store.count() == 0
        store.upsert("a-001", _make_record("a-001"))
        store.upsert("a-002", _make_record("a-002"))
        assert store.count() == 2

    def test_list_acks_newest_first(self) -> None:
        store = InMemoryAckStore()
        store.upsert("a-001", _make_record("a-001"))
        store.upsert("a-002", _make_record("a-002"))
        store.upsert("a-003", _make_record("a-003"))
        items = store.list_acks(limit=10)
        assert [r["anomaly_id"] for r in items] == ["a-003", "a-002", "a-001"]

    def test_list_acks_pagination(self) -> None:
        store = InMemoryAckStore()
        for i in range(5):
            store.upsert(f"a-{i:03d}", _make_record(f"a-{i:03d}"))
        page = store.list_acks(limit=2, offset=1)
        assert len(page) == 2

    def test_eviction(self) -> None:
        store = InMemoryAckStore(max_records=3)
        for i in range(5):
            store.upsert(f"a-{i:03d}", _make_record(f"a-{i:03d}"))
        assert store.count() == 3
        assert store.get("a-000") is None
        assert store.get("a-001") is None
        assert store.get("a-004") is not None

    def test_list_acks_with_filter(self) -> None:
        store = InMemoryAckStore()
        store.upsert("a-001", _make_record("a-001", acknowledged_by="kirk"))
        store.upsert("a-002", _make_record("a-002", acknowledged_by="spock"))
        items = store.list_acks(filters={"acknowledged_by": "kirk"})
        assert len(items) == 1
        assert items[0]["acknowledged_by"] == "kirk"

    def test_count_with_filter(self) -> None:
        store = InMemoryAckStore()
        store.upsert("a-001", _make_record("a-001", acknowledged_by="kirk"))
        store.upsert("a-002", _make_record("a-002", acknowledged_by="spock"))
        assert store.count(filters={"acknowledged_by": "kirk"}) == 1

    def test_protocol_conformance(self) -> None:
        store = InMemoryAckStore()
        assert isinstance(store, AckStore)


# ── SqliteAckStore ──────────────────────────────────────────────────────────


class TestSqliteAckStore:
    def test_schema_creation(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        assert store.count() == 0

    def test_upsert_and_get(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        rec = _make_record("a-001")
        store.upsert("a-001", rec)
        got = store.get("a-001")
        assert got is not None
        assert got["anomaly_id"] == "a-001"
        assert got["acknowledged_by"] == "ui"

    def test_get_returns_none_for_unknown(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        assert store.get("nope") is None

    def test_upsert_updates_existing(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _make_record("a-001", note="first"))
        store.upsert("a-001", _make_record("a-001", note="second"))
        got = store.get("a-001")
        assert got is not None
        assert got["note"] == "second"
        assert store.count() == 1

    def test_count(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _make_record("a-001"))
        store.upsert("a-002", _make_record("a-002"))
        assert store.count() == 2

    def test_list_acks_ordering(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _make_record("a-001"))
        store.upsert("a-002", _make_record("a-002"))
        items = store.list_acks(limit=10)
        assert len(items) == 2

    def test_list_acks_pagination(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        for i in range(5):
            store.upsert(f"a-{i:03d}", _make_record(f"a-{i:03d}"))
        page = store.list_acks(limit=2, offset=1)
        assert len(page) == 2

    def test_eviction(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db, max_records=3)
        for i in range(5):
            store.upsert(f"a-{i:03d}", _make_record(f"a-{i:03d}"))
        assert store.count() == 3

    def test_wal_mode(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        conn = store._connect()
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
        finally:
            conn.close()

    def test_list_acks_filter_acknowledged_by(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _make_record("a-001", acknowledged_by="kirk"))
        store.upsert("a-002", _make_record("a-002", acknowledged_by="spock"))
        items = store.list_acks(filters={"acknowledged_by": "kirk"})
        assert len(items) == 1
        assert items[0]["acknowledged_by"] == "kirk"

    def test_count_with_filter(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _make_record("a-001", acknowledged_by="kirk"))
        store.upsert("a-002", _make_record("a-002", acknowledged_by="spock"))
        assert store.count(filters={"acknowledged_by": "kirk"}) == 1

    def test_thread_safety(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db, max_records=200)

        def _upsert(i: int) -> None:
            store.upsert(f"a-{i:04d}", _make_record(f"a-{i:04d}"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(_upsert, range(50)))

        assert store.count() == 50

    def test_creates_parent_directory(self, tmp_path: object) -> None:
        db = str(tmp_path / "sub" / "dir" / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _make_record("a-001"))
        assert store.count() == 1

    def test_protocol_conformance(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = SqliteAckStore(db_path=db)
        assert isinstance(store, AckStore)


# ── Factory ─────────────────────────────────────────────────────────────────


class TestCreateAckStore:
    def test_returns_sqlite_when_db_path(self, tmp_path: object) -> None:
        db = str(tmp_path / "test.db")  # type: ignore[operator]
        store = create_ack_store(db_path=db, max_records=100)
        assert isinstance(store, SqliteAckStore)

    def test_returns_inmemory_when_none(self) -> None:
        store = create_ack_store(db_path=None, max_records=100)
        assert isinstance(store, InMemoryAckStore)

    def test_returns_inmemory_when_empty_string(self) -> None:
        store = create_ack_store(db_path="", max_records=100)
        assert isinstance(store, InMemoryAckStore)

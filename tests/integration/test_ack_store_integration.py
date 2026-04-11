"""Integration tests for AckStore SQLite persistence."""
from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone

import pytest

from mcp_server.ack_store import SqliteAckStore


def _ack_record(anomaly_id: str, by: str = "ui", note: str = "") -> dict:
    """Build a minimal ACK record dict."""
    return {
        "anomaly_id": anomaly_id,
        "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        "acknowledged_by": by,
        "note": note,
    }


@pytest.mark.integration
class TestAckStoreIntegration:
    def test_sqlite_persist_across_instances(self, tmp_path):
        db = str(tmp_path / "ack.db")
        store1 = SqliteAckStore(db_path=db)
        store1.upsert("a-001", _ack_record("a-001", by="kirk", note="test"))
        del store1
        store2 = SqliteAckStore(db_path=db)
        record = store2.get("a-001")
        assert record is not None
        assert record["acknowledged_by"] == "kirk"

    def test_sqlite_upsert_updates(self, tmp_path):
        db = str(tmp_path / "ack.db")
        store = SqliteAckStore(db_path=db)
        store.upsert("a-001", _ack_record("a-001", note="first"))
        store.upsert("a-001", _ack_record("a-001", note="second"))
        assert store.get("a-001")["note"] == "second"
        assert store.count() == 1

    def test_sqlite_filter_by_operator(self, tmp_path):
        db = str(tmp_path / "ack.db")
        store = SqliteAckStore(db_path=db)
        for i, op in enumerate(["kirk", "spock", "kirk", "bones", "kirk"]):
            store.upsert(f"a-{i:03d}", _ack_record(f"a-{i:03d}", by=op))
        items = store.list_acks(filters={"acknowledged_by": "kirk"})
        assert len(items) == 3

    def test_sqlite_pagination(self, tmp_path):
        db = str(tmp_path / "ack.db")
        store = SqliteAckStore(db_path=db)
        for i in range(25):
            store.upsert(f"a-{i:03d}", _ack_record(f"a-{i:03d}"))
        page1 = store.list_acks(limit=10, offset=0)
        page2 = store.list_acks(limit=10, offset=10)
        assert len(page1) == 10
        assert len(page2) == 10
        ids1 = {r["anomaly_id"] for r in page1}
        ids2 = {r["anomaly_id"] for r in page2}
        assert ids1.isdisjoint(ids2)

    def test_sqlite_eviction(self, tmp_path):
        db = str(tmp_path / "ack.db")
        store = SqliteAckStore(db_path=db, max_records=5)
        for i in range(8):
            store.upsert(f"a-{i:03d}", _ack_record(f"a-{i:03d}"))
        assert store.count() == 5

    def test_sqlite_concurrent_access(self, tmp_path):
        db = str(tmp_path / "ack.db")
        store = SqliteAckStore(db_path=db, max_records=200)

        def _upsert(i):
            store.upsert(f"a-{i:04d}", _ack_record(f"a-{i:04d}"))

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(_upsert, range(50)))
        assert store.count() == 50

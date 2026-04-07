"""Integration tests for SessionStore SQLite persistence."""
from __future__ import annotations

import pytest

from mcp_server.session_store import SqliteSessionStore


@pytest.mark.integration
class TestSessionStoreIntegration:
    def test_session_persist_across_instances(self, tmp_path):
        db = str(tmp_path / "sess.db")
        store1 = SqliteSessionStore(db_path=db)
        sid = store1.create_session(operator_id="kirk")
        store1.append_message(sid, {"role": "user", "text": "hello"})
        del store1
        store2 = SqliteSessionStore(db_path=db)
        msgs = store2.get_messages(sid)
        assert len(msgs) == 1
        assert msgs[0]["text"] == "hello"

    def test_session_cleanup_expired(self, tmp_path):
        db = str(tmp_path / "sess.db")
        store = SqliteSessionStore(db_path=db)
        for _ in range(3):
            store.create_session()
        deleted = store.cleanup_expired(ttl_seconds=0)
        assert deleted == 3

    def test_multiple_sessions_isolated(self, tmp_path):
        db = str(tmp_path / "sess.db")
        store = SqliteSessionStore(db_path=db)
        s1 = store.create_session()
        s2 = store.create_session()
        store.append_message(s1, {"role": "user", "text": "msg-a"})
        store.append_message(s2, {"role": "user", "text": "msg-b"})
        assert store.get_messages(s1)[0]["text"] == "msg-a"
        assert store.get_messages(s2)[0]["text"] == "msg-b"

    def test_session_nonexistent_returns_empty(self, tmp_path):
        db = str(tmp_path / "sess.db")
        store = SqliteSessionStore(db_path=db)
        assert store.get_messages("nonexistent-id") == []

    def test_session_append_to_nonexistent_is_noop(self, tmp_path):
        db = str(tmp_path / "sess.db")
        store = SqliteSessionStore(db_path=db)
        store.append_message("bad-id", {"role": "user", "text": "ghost"})
        assert store.get_messages("bad-id") == []

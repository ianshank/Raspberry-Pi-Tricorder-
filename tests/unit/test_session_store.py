"""Tests for mcp_server.session_store -- InMemory and SQLite backends."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mcp_server.session_store import (
    InMemorySessionStore,
    SessionStore,
    SqliteSessionStore,
    create_session_store,
)


# ── InMemorySessionStore ──────────────────────────────────────────────────


class TestInMemorySessionStore:
    def test_create_session_returns_valid_id(self) -> None:
        store = InMemorySessionStore()
        sid = store.create_session("op-1")
        assert sid.startswith("sess-")
        assert len(sid) == 21  # "sess-" + 16 hex chars

    def test_get_messages_empty_for_new_session(self) -> None:
        store = InMemorySessionStore()
        sid = store.create_session()
        assert store.get_messages(sid) == []

    def test_append_and_get_messages(self) -> None:
        store = InMemorySessionStore()
        sid = store.create_session("op-1")
        msg1 = {"role": "user", "content": "hello"}
        msg2 = {"role": "assistant", "content": "hi there"}
        store.append_message(sid, msg1)
        store.append_message(sid, msg2)
        messages = store.get_messages(sid)
        assert len(messages) == 2
        assert messages[0] == msg1
        assert messages[1] == msg2

    def test_get_session_info(self) -> None:
        store = InMemorySessionStore()
        sid = store.create_session("op-42")
        store.append_message(sid, {"role": "user", "content": "test"})
        info = store.get_session_info(sid)
        assert info is not None
        assert info["session_id"] == sid
        assert info["operator_id"] == "op-42"
        assert info["message_count"] == 1
        assert "created_at" in info
        assert "updated_at" in info

    def test_get_messages_nonexistent_returns_empty(self) -> None:
        store = InMemorySessionStore()
        assert store.get_messages("sess-doesnotexist") == []

    def test_get_session_info_nonexistent_returns_none(self) -> None:
        store = InMemorySessionStore()
        assert store.get_session_info("sess-nope") is None

    def test_cleanup_expired_removes_old_keeps_recent(self) -> None:
        store = InMemorySessionStore()
        # Create a session and backdate its updated_at
        old_sid = store.create_session("old-op")
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=7200)).isoformat()
        store._sessions[old_sid]["updated_at"] = old_ts

        recent_sid = store.create_session("new-op")

        deleted = store.cleanup_expired(ttl_seconds=3600)
        assert deleted == 1
        assert store.get_session_info(old_sid) is None
        assert store.get_session_info(recent_sid) is not None

    def test_append_message_to_nonexistent_is_noop(self) -> None:
        store = InMemorySessionStore()
        # Should not raise
        store.append_message("sess-nope", {"role": "user", "content": "x"})

    def test_protocol_conformance(self) -> None:
        store = InMemorySessionStore()
        assert isinstance(store, SessionStore)


# ── SqliteSessionStore ────────────────────────────────────────────────────


class TestSqliteSessionStore:
    def test_create_session_returns_valid_id(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        sid = store.create_session("op-1")
        assert sid.startswith("sess-")
        assert len(sid) == 21

    def test_get_messages_empty_for_new_session(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        sid = store.create_session()
        assert store.get_messages(sid) == []

    def test_append_and_get_messages(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        sid = store.create_session("op-1")
        msg1 = {"role": "user", "content": "hello"}
        msg2 = {"role": "assistant", "content": "hi"}
        store.append_message(sid, msg1)
        store.append_message(sid, msg2)
        messages = store.get_messages(sid)
        assert len(messages) == 2
        assert messages[0] == msg1
        assert messages[1] == msg2

    def test_get_session_info(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        sid = store.create_session("op-99")
        store.append_message(sid, {"role": "user", "content": "test"})
        info = store.get_session_info(sid)
        assert info is not None
        assert info["session_id"] == sid
        assert info["operator_id"] == "op-99"
        assert info["message_count"] == 1
        assert "created_at" in info
        assert "updated_at" in info

    def test_get_messages_nonexistent_returns_empty(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        assert store.get_messages("sess-doesnotexist") == []

    def test_get_session_info_nonexistent_returns_none(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        assert store.get_session_info("sess-nope") is None

    def test_cleanup_expired_removes_old_keeps_recent(self, tmp_path) -> None:
        import sqlite3

        db_path = str(tmp_path / "sessions.db")
        store = SqliteSessionStore(db_path)

        old_sid = store.create_session("old-op")
        recent_sid = store.create_session("new-op")

        # Backdate the old session directly in SQLite
        old_ts = (datetime.now(timezone.utc) - timedelta(seconds=7200)).isoformat()
        conn = sqlite3.connect(db_path)
        conn.execute(
            "UPDATE chat_sessions SET updated_at = ? WHERE session_id = ?",
            (old_ts, old_sid),
        )
        conn.commit()
        conn.close()

        deleted = store.cleanup_expired(ttl_seconds=3600)
        assert deleted == 1
        assert store.get_session_info(old_sid) is None
        assert store.get_session_info(recent_sid) is not None

    def test_append_message_to_nonexistent_is_noop(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        # Should not raise
        store.append_message("sess-nope", {"role": "user", "content": "x"})

    def test_protocol_conformance(self, tmp_path) -> None:
        store = SqliteSessionStore(str(tmp_path / "sessions.db"))
        assert isinstance(store, SessionStore)

    def test_parent_dir_creation(self, tmp_path) -> None:
        nested = tmp_path / "a" / "b" / "c" / "sessions.db"
        store = SqliteSessionStore(str(nested))
        sid = store.create_session()
        assert store.get_messages(sid) == []


# ── Factory ───────────────────────────────────────────────────────────────


class TestCreateSessionStore:
    def test_returns_sqlite_when_path_given(self, tmp_path) -> None:
        store = create_session_store(str(tmp_path / "s.db"))
        assert isinstance(store, SqliteSessionStore)

    def test_returns_inmemory_when_no_path(self) -> None:
        store = create_session_store()
        assert isinstance(store, InMemorySessionStore)

    def test_returns_inmemory_when_empty_string(self) -> None:
        store = create_session_store("")
        assert isinstance(store, InMemorySessionStore)

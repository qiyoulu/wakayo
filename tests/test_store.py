"""Test the wakayo.store module."""
import os
import tempfile
from pathlib import Path

import pytest

from wakayo.store import (
    add_entry,
    compact,
    connect,
    db_path,
    export_markdown,
    get_entry,
    init_db,
    list_entries,
    now_ts,
    promote_entry,
    query,
    stats,
    wakayo_dir,
)


@pytest.fixture
def db_conn():
    """Create a temporary database connection for each test."""
    # Save and clear WAKAYO_DIR to ensure isolation
    old_wakayo_dir = os.environ.get("WAKAYO_DIR")
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["WAKAYO_DIR"] = tmpdir
        try:
            path = db_path()
            conn = connect(path)
            init_db(conn)
            yield conn
        finally:
            conn.close()
            # Restore environment
            if old_wakayo_dir is None:
                os.environ.pop("WAKAYO_DIR", None)
            else:
                os.environ["WAKAYO_DIR"] = old_wakayo_dir


def test_add_entry(db_conn):
    """Test adding an entry."""
    eid = add_entry(db_conn, "test content", source="test", tags="tag1,tag2")
    assert isinstance(eid, int)
    assert eid > 0

    # Check that we can get it back
    entry = get_entry(db_conn, eid)
    assert entry is not None
    assert entry["content"] == "test content"
    assert entry["source"] == "test"
    assert entry["tags"] == "tag1,tag2"
    assert entry["promoted"] == 0


def test_get_entry(db_conn):
    """Test getting an entry."""
    eid = add_entry(db_conn, "to get", source="test")
    entry = get_entry(db_conn, eid)
    assert entry["content"] == "to get"

    # Non-existent entry
    assert get_entry(db_conn, 99999) is None


def test_promote_entry(db_conn):
    """Test promoting an entry."""
    eid = add_entry(db_conn, "to promote", source="test")
    assert get_entry(db_conn, eid)["promoted"] == 0

    promoted = promote_entry(db_conn, eid)
    assert promoted["promoted"] == 1

    # Check that the promotion stuck
    assert get_entry(db_conn, eid)["promoted"] == 1


def test_query(db_conn):
    """Test FTS5 query."""
    # Add a few entries
    add_entry(db_conn, "alpha beta gamma", source="test", tags="a,b")
    add_entry(db_conn, "beta gamma delta", source="test", tags="b,c")
    add_entry(db_conn, "gamma delta epsilon", source="other", tags="c,d")

    # Query for "beta" should return two entries
    results = query(db_conn, "beta")
    assert len(results) == 2
    assert all("beta" in r["content"] for r in results)

    # Query with source filter
    results = query(db_conn, "gamma", source="test")
    assert len(results) == 2  # first two have gamma and source=test

    # Query with tags filter
    results = query(db_conn, "gamma", tags="b")
    assert len(results) == 2  # first two have tag b

    # Query with date range (using now_ts)
    now = now_ts()
    results = query(db_conn, "gamma", after=now - 10, before=now + 10)
    assert len(results) == 3  # all are within 10 seconds of now

    # Query with limit
    results = query(db_conn, "gamma", limit=1)
    assert len(results) == 1


def test_list_entries(db_conn):
    """Test listing entries."""
    # Add three entries with a small delay to ensure different timestamps
    e1 = add_entry(db_conn, "first", source="test")
    e2 = add_entry(db_conn, "second", source="test")
    e3 = add_entry(db_conn, "third", source="test")

    # List all
    results = list_entries(db_conn)
    assert len(results) == 3
    # Should be in descending order of creation (most recent first)
    assert results[0]["id"] == e3
    assert results[1]["id"] == e2
    assert results[2]["id"] == e1

    # List with limit
    results = list_entries(db_conn, limit=2)
    assert len(results) == 2
    assert results[0]["id"] == e3
    assert results[1]["id"] == e2

    # List with source filter
    results = list_entries(db_conn, source="test")
    assert len(results) == 3

    # List with source filter that doesn't match
    results = list_entries(db_conn, source="other")
    assert len(results) == 0


def test_compact(db_conn):
    """Test compacting (deleting expired entries)."""
    now = now_ts()
    # Add an entry that expires in the past
    eid_past = add_entry(db_conn, "expired", source="test", expires_after_days=-1)
    # Add an entry that expires in the future
    eid_future = add_entry(db_conn, "not expired", source="test", expires_after_days=1)
    # Add an entry with no expiration
    eid_noexp = add_entry(db_conn, "no expiration", source="test")

    # Before compact, we should have three entries
    assert stats(db_conn)["total"] == 3

    # Compact should remove the expired one
    deleted = compact(db_conn)
    assert deleted == 1

    # After compact, we should have two entries
    assert stats(db_conn)["total"] == 2

    # Check that the expired one is gone and the others remain
    assert get_entry(db_conn, eid_past) is None
    assert get_entry(db_conn, eid_future) is not None
    assert get_entry(db_conn, eid_noexp) is not None


def test_stats(db_conn):
    """Test statistics."""
    # Start with empty
    s = stats(db_conn)
    assert s["total"] == 0
    assert s["total_chars"] == 0
    assert s["expired"] == 0
    assert s["promoted"] == 0
    assert s["by_source"] == []

    # Add a few entries
    e1 = add_entry(db_conn, "hello world", source="test", tags="greeting")
    e2 = add_entry(db_conn, "another", source="other")
    e3 = add_entry(db_conn, "a third", source="test", expires_after_days=1)

    # Promote one
    promote_entry(db_conn, e2)

    s = stats(db_conn)
    assert s["total"] == 3
    # "hello world" (11) + "another" (7) + "a third" (7) = 25
    assert s["total_chars"] == 25
    assert s["expired"] == 0  # none expired yet
    assert s["promoted"] == 1  # only e2 promoted
    # by_source: test:2, other:1
    assert set(s["by_source"]) == {("test", 2), ("other", 1)}


def test_export_markdown(db_conn):
    """Test exporting to markdown."""
    eid = add_entry(db_conn, "export me", source="test", tags="to,export")
    promote_entry(db_conn, eid)

    md = export_markdown(db_conn)
    assert "# wakayo export" in md
    assert f"## id={eid}  (test)" in md
    assert "tags: to,export" in md
    assert "promoted: yes" in md
    assert "export me" in md
    assert "§" in md  # the section separator

    # Test with a path
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.md"
        export_markdown(db_conn, path=path)
        assert path.exists()
        content = path.read_text()
        assert "# wakayo export" in content
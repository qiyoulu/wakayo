"""Test the wakayo CLI."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def isolated_env():
    """Provide a clean environment with a temporary WAKAYO_DIR."""
    old_env = dict(os.environ)
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["WAKAYO_DIR"] = tmpdir
        yield
    # Restore
    os.environ.clear()
    os.environ.update(old_env)


def run_wakayo(args, input_text=None, env=None):
    """Run the wakayo CLI and return (stdout, stderr, returncode)."""
    if env is None:
        env = os.environ.copy()
    # Find the wakayo console script in the same directory as the current python
    wakayo_cmd = Path(sys.executable).parent / "wakayo"
    if not wakayo_cmd.exists():
        # Fallback to just "wakoya" and hope it's in PATH
        wakayo_cmd = "wakayo"
    proc = subprocess.run(
        [str(wakayo_cmd), *args],
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
    )
    return proc.stdout, proc.stderr, proc.returncode


def test_cli_add(isolated_env):
    """Test `wakayo add` via the CLI."""
    out, err, code = run_wakayo(["add", "--content", "hello test", "--source", "hermes"])
    assert code == 0
    assert "added id=" in out
    # extract the id
    eid = int(out.split("=")[1].split()[0])

    # verify it exists
    out, err, code = run_wakayo(["get", str(eid)])
    assert code == 0
    assert "hello test" in out
    assert "source=hermes" in out


def test_cli_query(isolated_env):
    """Test `wakayo query` via the CLI."""
    # Add two entries
    run_wakayo(["add", "--content", "alpha beta", "--source", "hermes"])
    run_wakayo(["add", "--content", "beta gamma", "--source", "hermes"])

    out, err, code = run_wakayo(["query", "beta"])
    assert code == 0
    assert "alpha beta" in out
    assert "beta gamma" in out


def test_cli_list(isolated_env):
    """Test `wakayo list` via the CLI."""
    run_wakayo(["add", "--content", "first", "--source", "hermes"])
    run_wakayo(["add", "--content", "second", "--source", "hermes"])

    out, err, code = run_wakayo(["list", "--limit", "1"])
    assert code == 0
    # Should return the most recent entry
    assert "second" in out
    assert "first" not in out  # only one due to limit


def test_cli_promote(isolated_env):
    """Test `wakayo promote` via the CLI."""
    out, err, code = run_wakayo(["add", "--content", "to promote", "--source", "hermes"])
    assert code == 0
    eid = int(out.split("=")[1].split()[0])

    out, err, code = run_wakayo(["promote", str(eid)])
    assert code == 0
    assert f"promoted id={eid}" in out
    assert "(flag set in DB only" in out


def test_cli_compact(isolated_env):
    """Test `wakayo compact` via the CLI."""
    now = int(__import__("time").time())
    # Add an expired entry (expires in the past)
    run_wakayo(["add", "--content", "to delete", "--source", "hermes", "--expires-days", "-1"])
    # Add a non-expired entry
    run_wakayo(["add", "--content", "to keep", "--source", "hermes", "--expires-days", "30"])

    out, err, code = run_wakayo(["compact"])
    assert code == 0
    assert "compacted 1 expired entries" in out

    # Verify the expired one is gone and the other remains
    out, err, code = run_wakayo(["list"])
    assert code == 0
    assert "to delete" not in out
    assert "to keep" in out


def test_cli_stats(isolated_env):
    """Test `wakayo stats` via the CLI."""
    out, err, code = run_wakayo(["stats"])
    assert code == 0
    assert "total entries:   0" in out

    run_wakayo(["add", "--content", "one", "--source", "hermes"])
    run_wakayo(["add", "--content", "two", "--source", "manual"])

    out, err, code = run_wakayo(["stats"])
    assert code == 0
    assert "total entries:   2" in out
    assert "by source:" in out
    assert "hermes" in out
    assert "manual" in out


def test_cli_export(isolated_env):
    """Test `wakayo export` via the CLI."""
    out, err, code = run_wakayo(["add", "--content", "to export", "--source", "hermes"])
    assert code == 0

    out, err, code = run_wakayo(["export"])
    assert code == 0
    assert "# wakayo export" in out
    assert "to export" in out
    assert "§" in out


def test_cli_help(isolated_env):
    """Test `wakayo` with no arguments prints help."""
    out, err, code = run_wakayo([])
    assert code == 0  # our CLI prints help and returns 0
    assert "usage: wakayo" in out
    assert "add" in out
    assert "query" in out
    assert "list" in out
    assert "promote" in out
    assert "compact" in out
    assert "stats" in out
    assert "export" in out
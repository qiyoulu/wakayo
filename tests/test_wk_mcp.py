#!/usr/bin/env python3
"""Test the wakayo MCP server (wk.py) via subprocess."""
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


def run_wk(args, input_text=None, env=None):
    """Run wk.py as a subprocess and return (stdout, stderr, returncode)."""
    if env is None:
        env = os.environ.copy()
    wk_path = Path(__file__).parent / "wk.py"
    proc = subprocess.run(
        [sys.executable, str(wk_path), *args],
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
    )
    return proc.stdout, proc.stderr, proc.returncode


def test_wk_add(isolated_env):
    """Test wk.py add command."""
    out, err, code = run_wk(["add", "--content", "hello test", "--source", "hermes"])
    assert code == 0
    assert "added id=" in out
    # extract the id
    eid = int(out.split("=")[1].split()[0])

    # verify it exists
    out, err, code = run_wk(["get", str(eid)])
    assert code == 0
    assert "hello test" in out
    assert "source=hermes" in out


def test_wk_query(isolated_env):
    """Test wk.py query command."""
    # Add two entries
    run_wk(["add", "--content", "alpha beta", "--source", "hermes"])
    run_wk(["add", "--content", "beta gamma", "--source", "hermes"])

    out, err, code = run_wk(["query", "beta"])
    assert code == 0
    assert "alpha beta" in out
    assert "beta gamma" in out


def test_wk_list(isolated_env):
    """Test wk.py list command."""
    run_wk(["add", "--content", "first", "--source", "hermes"])
    run_wk(["add", "--content", "second", "--source", "hermes"])

    out, err, code = run_wk(["list", "--limit", "1"])
    assert code == 0
    # Should return the most recent entry
    assert "second" in out
    assert "first" not in out  # only one due to limit


def test_wk_promote(isolated_env):
    """Test wk.py promote command."""
    out, err, code = run_wk(["add", "--content", "to promote", "--source", "hermes"])
    assert code == 0
    eid = int(out.split("=")[1].split()[0])

    out, err, code = run_wk(["promote", str(eid)])
    assert code == 0
    assert f"promoted id={eid}" in out
    assert "(flag set in DB only" in out


def test_wk_compact(isolated_env):
    """Test wk.py compact command."""
    now = int(__import__("time").time())
    # Add an expired entry (expires in the past)
    run_wk(["add", "--content", "to delete", "--source", "hermes", "--expires-days", "-1"])
    # Add a non-expired entry
    run_wk(["add", "--content", "to keep", "--source", "hermes", "--expires-days", "30"])

    out, err, code = run_wk(["compact"])
    assert code == 0
    assert "compacted 1 expired entries" in out

    # Verify the expired one is gone and the other remains
    out, err, code = run_wk(["list"])
    assert code == 0
    assert "to delete" not in out
    assert "to keep" in out


def test_wk_stats(isolated_env):
    """Test wk.py stats command."""
    out, err, code = run_wk(["stats"])
    assert code == 0
    assert "total entries:   0" in out

    run_wk(["add", "--content", "one", "--source", "hermes"])
    run_wk(["add", "--content", "two", "--source", "manual"])

    out, err, code = run_wk(["stats"])
    assert code == 0
    assert "total entries:   2" in out
    assert "by source:" in out
    assert "hermes" in out
    assert "manual" in out


def test_wk_export(isolated_env):
    """Test wk.py export command."""
    out, err, code = run_wk(["add", "--content", "to export", "--source", "hermes"])
    assert code == 0

    out, err, code = run_wk(["export"])
    assert code == 0
    assert "# wakayo export" in out
    assert "to export" in out
    assert "§" in out


def test_wk_help(isolated_env):
    """Test wk.py with no arguments prints help."""
    out, err, code = run_wk([])
    assert code == 0  # our CLI prints help and returns 0
    assert "usage: wakayo" in out
    assert "add" in out
    assert "query" in out
    assert "list" in out
    assert "promote" in out
    assert "compact" in out
    assert "stats" in out
    assert "export" in out


def test_wk_mcp_tools_list():
    """Test wk.py MCP server tools/list."""
    # Prepare environment with a temporary WAKAYO_DIR
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["WAKAYO_DIR"] = tmpdir
        wk_path = Path(__file__).parent / "wk.py"
        # Provide a minimal MCP initialize then tools/list
        init_req = '{"jsonrpc":"2.0","id":1,"method":"initialize"}'
        list_req = '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
        input_text = f"{init_req}\n{list_req}\n"
        proc = subprocess.run(
            [sys.executable, str(wk_path), *[]],
            input=input_text,
            text=True,
            capture_output=True,
            env=env,
        )
        out, err, code = proc.stdout, proc.stderr, proc.returncode
        assert code == 0
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        # Should have two JSON-RPC responses
        assert len(lines) >= 2
        # Parse the second line (tools/list response)
        resp = json.loads(lines[1])
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 2
        assert "result" in resp
        assert "tools" in resp["result"]
        tool_names = [t["name"] for t in resp["result"]["tools"]]
        expected = {
            "wakayo_add",
            "wakayo_query",
            "wakayo_list",
            "wakayo_get",
            "wakayo_promote",
            "wakayo_compact",
            "wakayo_stats",
        }
        assert set(tool_names) == expected


def test_wk_mcp_tool_call_add():
    """Test wk.py MCP server wakayo_add tool call."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env = os.environ.copy()
        env["WAKAYO_DIR"] = tmpdir
        init_req = '{"jsonrpc":"2.0","id":1,"method":"initialize"}'
        add_req = (
            '{"jsonrpc":"2.0","id":2,"method":"tools/call",'
            '"params":{"name":"wakayo_add","arguments":{"content":"hello mcp","source":"hermes"}}}'
        )
        list_req = '{"jsonrpc":"2.0","id":3,"method":"tools/list"}'
        input_text = f"{init_req}\n{add_req}\n{list_req}\n"
        wk_path = Path(__file__).parent / "wk.py"
        proc = subprocess.run(
            [sys.executable, str(wk_path), *[]],
            input=input_text,
            text=True,
            capture_output=True,
            env=env,
        )
        out, err, code = proc.stdout, proc.stderr, proc.returncode
        assert code == 0
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        assert len(lines) >= 3
        # Parse the add response (second line)
        add_resp = json.loads(lines[1])
        assert add_resp["jsonrpc"] == "2.0"
        assert add_resp["id"] == 2
        assert "result" in add_resp
        assert "content" in add_resp["result"]
        # Should be a list of content blocks
        content_blocks = add_resp["result"]["content"]
        assert isinstance(content_blocks, list)
        assert len(content_blocks) == 1
        assert content_blocks[0]["type"] == "text"
        assert "added id=" in content_blocks[0]["text"]
        # extract id and verify via get
        eid_line = content_blocks[0]["text"]
        eid = int(eid_line.split("=")[1].split()[0])
        get_req = f'{{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{{"name":"wakayo_get","arguments":{{"id":{eid}}}}}}}'
        input_text2 = f"{init_req}\n{get_req}\n"
        proc2 = subprocess.run(
            [sys.executable, str(wk_path), *[]],
            input=input_text2,
            text=True,
            capture_output=True,
            env=env,
        )
        out2, err2, code2 = proc2.stdout, proc2.stderr, proc2.returncode
        assert code2 == 0
        lines2 = [line.strip() for line in out2.splitlines() if line.strip()]
        get_resp = json.loads(lines2[1])
        assert get_resp["result"]["content"][0]["text"] == "hello mcp"


if __name__ == "__main__":
    # Allow running the test manually for debugging
    pytest.main([__file__, "-v"])
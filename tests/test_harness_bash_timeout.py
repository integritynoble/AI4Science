from __future__ import annotations

import time
from ai4science.harness.tools import shell


def test_bash_times_out_on_hang(tmp_path, monkeypatch):
    monkeypatch.setattr(shell, "BASH_TIMEOUT_SECONDS", 1)
    start = time.monotonic()
    out = shell.bash(tmp_path, cmd="sleep 30")
    elapsed = time.monotonic() - start
    assert "timed out" in out.lower()
    assert elapsed < 10


def test_bash_still_streams_and_returns(tmp_path):
    chunks = []
    out = shell.bash(tmp_path, cmd="printf 'a\\nb\\n'", _sink=chunks.append)
    assert "a" in out and "b" in out
    assert "".join(chunks) and "".join(chunks) in out


def test_bash_nonzero_exit_preserved(tmp_path):
    out = shell.bash(tmp_path, cmd="exit 3")
    assert "exit code 3" in out.lower()

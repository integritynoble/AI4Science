from __future__ import annotations

import time
from ai4science.harness.tools import shell


def test_bash_times_out_on_hang(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_BASH_TIMEOUT", "1")
    start = time.monotonic()
    out = shell.bash(tmp_path, cmd="sleep 30")
    elapsed = time.monotonic() - start
    assert "timed out" in out.lower()
    # killing the process group + closing stdout unblocks the reader promptly,
    # so the call returns close to the 1s timeout — not after the 5s join grace.
    assert elapsed < 4


def test_bash_times_out_kills_child_process(tmp_path, monkeypatch):
    """The actual command (a child of the shell) is killed, not orphaned."""
    monkeypatch.setenv("AI4SCIENCE_BASH_TIMEOUT", "1")
    marker = tmp_path / "alive.txt"
    # write a marker after a delay; if the tree is truly killed, it never appears
    shell.bash(tmp_path, cmd=f"sleep 3 && echo done > {marker}")
    time.sleep(3.5)
    assert not marker.exists()


def test_bash_still_streams_and_returns(tmp_path):
    chunks = []
    out = shell.bash(tmp_path, cmd="printf 'a\\nb\\n'", _sink=chunks.append)
    assert "a" in out and "b" in out
    assert "".join(chunks) and "".join(chunks) in out


def test_bash_nonzero_exit_preserved(tmp_path):
    out = shell.bash(tmp_path, cmd="exit 3")
    assert "exit code 3" in out.lower()

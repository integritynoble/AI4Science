from pathlib import Path
from ai4science.harness.tools import shell, default_registry
from ai4science.harness.tools.base import Tool


def test_bash_streams_to_sink(tmp_path):
    chunks = []
    out = shell.bash(tmp_path, cmd="printf 'a\\nb\\nc\\n'", _sink=chunks.append)
    assert out.count("a") == 1 and "b" in out and "c" in out
    assert "".join(chunks).count("a") == 1
    assert "".join(chunks) == out or "".join(chunks) in out


def test_bash_without_sink_still_returns(tmp_path):
    out = shell.bash(tmp_path, cmd="echo hi")
    assert "hi" in out


def test_bash_tool_marked_streaming():
    reg = default_registry()
    assert reg.get("bash").streams is True
    assert reg.get("read").streams is False

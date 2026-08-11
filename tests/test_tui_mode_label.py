"""The mode label must reach the input box — I4 from the REPL-modes ledger.

The design calls the label the safety mechanism: `sarsi-worker ❯ ` in front of
the cursor is what tells the owner which program their next line feeds. Under
the full-screen composer the label used to be APPENDED to the transcript — one
line above the cursor, scrolling away with the output — while the composer kept
drawing its constructor-time `❯ `. A label a line above the cursor is a
caption, not a prompt.

Driven through a real PTY (same harness as test_tui_persistent_box): pyte
replays the byte stream, and the assertion is that the label and the text being
typed share a line — the label is IN the box, not above it.
"""
import os
import pty
import select
import sys
import time

import pytest

pyte = pytest.importorskip("pyte")
pytest.importorskip("prompt_toolkit")

_DRIVER = r'''
import os, sys
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui

fs = tui.FullScreen("claude-code")

def worker():
    # First read: top level, plain prompt.
    tui.read_input("❯ ", "claude-code", "demo-status")
    # Second read: the owner is now standing in a worker — the label must
    # reach the composer for whatever they type next.
    line = tui.read_input("sarsi-worker ❯ ", "claude-code", "demo-status")
    print("GOT:" + line)

fs.run(worker)
'''


def _spawn_and_drive(inputs, settle=0.6, total_timeout=12.0, driver=_DRIVER):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.environ["TERM"] = "xterm-256color"
        os.environ["PYTHONPATH"] = repo + os.pathsep + os.environ.get("PYTHONPATH", "")
        # The interpreter the importorskip guards above actually checked — not
        # whatever `python3` PATH happens to resolve to in the child.
        os.execv(sys.executable, [sys.executable, "-c", driver])
        os._exit(127)  # unreachable

    raw = bytearray()
    screen = pyte.Screen(100, 30)
    stream = pyte.ByteStream(screen)

    def _pump(deadline):
        while time.monotonic() < deadline:
            r, _, _ = select.select([fd], [], [], 0.1)
            if fd in r:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    return False
                if not chunk:
                    return False
                raw.extend(chunk)
                stream.feed(chunk)
        return True

    start = time.monotonic()
    _pump(start + settle)
    for data in inputs:
        os.write(fd, data)
        _pump(time.monotonic() + settle)
    _pump(start + total_timeout)
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.waitpid(pid, 0)
    except OSError:
        pass
    return bytes(raw), [ln.rstrip() for ln in screen.display]


def test_the_mode_label_reaches_the_input_box():
    # Enter the worker (first read consumes "hi"), then TYPE without sending:
    # the snapshot must show the label and the typed text on ONE line.
    raw, lines = _spawn_and_drive([b"hi\n", b"status please"])
    text = "\n".join(lines)
    labelled = [ln for ln in lines if "sarsi-worker ❯" in ln]
    assert labelled, f"the mode label never rendered:\n{text}"
    assert any("status please" in ln for ln in labelled), (
        "the label is not on the input line — it rendered as a caption "
        f"above the cursor instead:\n{text}")


def test_leaving_the_mode_takes_the_label_back_off():
    # After the labelled read, a plain-prompt read must NOT keep the stale
    # label in front of the cursor.
    driver = _DRIVER.replace(
        'print("GOT:" + line)',
        'print("GOT:" + line)\n    tui.read_input("\\u276f ", "claude-code", "demo-status")')
    raw, lines = _spawn_and_drive([b"hi\n", b"back at top\n", b"typing now"],
                                  driver=driver)
    text = "\n".join(lines)
    # "typing now" is echoed by the tty whether or not the child is alive, so
    # the claim below is only meaningful once the labelled read has rendered.
    # The label lives in the composer, which the plain-prompt read redraws over
    # — so look for it in the byte stream, not in the closing snapshot.
    assert "sarsi-worker ❯".encode() in raw, (
        "the driver never got as far as the labelled read — nothing here can "
        f"say whether the label comes back off:\n{text}")
    typing = [ln for ln in lines if "typing now" in ln]
    assert typing, f"never saw the typed text:\n{text}"
    assert all("sarsi-worker" not in ln for ln in typing), (
        f"the stale worker label is still on the input line:\n{text}")

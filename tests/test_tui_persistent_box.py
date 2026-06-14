"""The persistent composer (tui.run_full / FullScreen) stays pinned at the
bottom while the REPL worker streams output above it — Claude-Code parity.

Driven through a real PTY so prompt_toolkit renders for true; pyte replays the
byte stream into a virtual screen we can assert on.
"""
import os
import pty
import select
import time

import pytest

pyte = pytest.importorskip("pyte")
pytest.importorskip("prompt_toolkit")

# Child program: build a FullScreen, run a worker that reads one line, streams a
# few output lines, then reads again (proving the box survives the work) and
# exits. The worker reads through the MODULE-LEVEL read_input, which must route
# to the active screen's queue.
_DRIVER = r'''
import os, sys
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui

fs = tui.FullScreen("claude-code")

def worker():
    line = tui.read_input("❯ ", "claude-code", "demo-status")
    print("GOT:" + line)
    for i in range(1, 4):
        print("STREAM-LINE-%d" % i)
        sys.stdout.flush()
    # Second read: the box must still be alive here, mid-session.
    tui.read_input("❯ ", "claude-code", "demo-status")

fs.run(worker)
print("WORKER-DONE")
'''


def _spawn_and_drive(inputs, settle=0.6, total_timeout=12.0, driver=_DRIVER):
    """Fork a PTY child running the driver, feed `inputs` (list of bytes) with a
    pause between each, and return (raw_bytes, pyte_screen_lines)."""
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pid, fd = pty.fork()
    if pid == 0:  # child
        os.environ["TERM"] = "xterm-256color"
        os.environ["PYTHONPATH"] = repo + os.pathsep + os.environ.get("PYTHONPATH", "")
        os.execvp("python3", ["python3", "-c", driver])
        os._exit(127)  # unreachable

    raw = bytearray()
    screen = pyte.Screen(100, 30)
    stream = pyte.ByteStream(screen)

    def _pump(deadline):
        # Read until the deadline — DON'T bail on the first idle gap, or we stop
        # reading before prompt_toolkit finishes painting / responding.
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
    # let the app paint its first frame
    _pump(start + settle)
    for data in inputs:
        os.write(fd, data)
        _pump(time.monotonic() + settle)
    # drain to completion / timeout
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


def test_persistent_box_streams_and_survives():
    raw, lines = _spawn_and_drive([b"hello\n", b"/exit\n"])
    text = "\n".join(lines)

    # 1) NO alt-screen — that's what keeps native wheel-scroll + copy working.
    assert b"\x1b[?1049h" not in raw, "must not enter the alternate screen buffer"

    # 2) The worker actually received the routed input and streamed output.
    assert "GOT:hello" in text, f"input not routed to worker:\n{text}"
    assert "STREAM-LINE-3" in text, f"worker output missing:\n{text}"

    # 3) The composer box is present (top/bottom horizontal rules).
    assert any("─" in ln for ln in lines), f"box rule missing:\n{text}"

    # 4) The status line (mode + status) renders under the box.
    assert "ai4science" in text and "demo-status" in text, \
        f"status line missing:\n{text}"


def test_no_alt_screen_and_clean_exit():
    raw, lines = _spawn_and_drive([b"hello\n", b"/exit\n"])
    # The driver prints WORKER-DONE only if fs.run() returned (clean teardown).
    assert b"WORKER-DONE" in raw, "FullScreen.run did not return cleanly on /exit"
    # Alt-screen leave sequence should also be absent (never entered).
    assert b"\x1b[?1049l" not in raw


# Up-arrow recalls the last message for editing (Claude Code parity).
_DRIVER_UPARROW = r'''
import os, sys
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
os.environ["XDG_CONFIG_HOME"] = "/tmp/ai4s_uptest_cfg"
import shutil
shutil.rmtree("/tmp/ai4s_uptest_cfg", ignore_errors=True)
from ai4science.harness import tui
fs = tui.FullScreen("claude-code")
def worker():
    a = tui.read_input("X ", "claude-code", "demo")
    print("GOT1:" + a)
    b = tui.read_input("X ", "claude-code", "demo")   # we press Up then Enter here
    print("GOT2:" + b)
    tui.read_input("X ", "claude-code", "demo")
fs.run(worker)
'''


def test_up_arrow_recalls_last_message():
    # Send "first msg"; on the next empty prompt press Up (recall) then Enter.
    # Generous settle so the worker reaches the 2nd read + history persists
    # before Up is pressed (PTY timing).
    raw, lines = _spawn_and_drive(
        [b"first msg\r", b"\x1b[A", b"\r", b"/exit\r"],
        driver=_DRIVER_UPARROW, settle=1.2, total_timeout=16.0)
    text = "\n".join(lines)
    assert "GOT1:first msg" in text
    # The second send equals the recalled first message — Up pulled it back.
    assert "GOT2:first msg" in text, f"up-arrow did not recall the message:\n{text}"


def test_sent_message_stays_visible():
    # The echoed `❯ <msg>` must remain in the transcript after sending (the bug
    # was the old per-prompt input erasing itself).
    raw, lines = _spawn_and_drive([b"keep me visible\n", b"/exit\n"])
    assert any("keep me visible" in ln for ln in lines), \
        "sent message vanished from the transcript"

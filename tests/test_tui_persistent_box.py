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


def test_ctrl_p_recalls_last_message():
    # Ctrl-P is the conhost-safe history alternate (the legacy Windows console
    # can eat the ↑ escape sequence). It must recall the last message just like
    # ↑ does. \x10 == Ctrl-P.
    raw, lines = _spawn_and_drive(
        [b"first msg\r", b"\x10", b"\r", b"/exit\r"],
        driver=_DRIVER_UPARROW, settle=1.2, total_timeout=16.0)
    text = "\n".join(lines)
    assert "GOT1:first msg" in text
    assert "GOT2:first msg" in text, f"Ctrl-P did not recall the message:\n{text}"


def test_sent_message_stays_visible():
    # The echoed `❯ <msg>` must remain in the transcript after sending (the bug
    # was the old per-prompt input erasing itself).
    raw, lines = _spawn_and_drive([b"keep me visible\n", b"/exit\n"])
    assert any("keep me visible" in ln for ln in lines), \
        "sent message vanished from the transcript"


# The picker (select → request_choice) must navigate via arrow, j/k AND digit.
# On Windows the hidden input box used to keep focus so NOTHING navigated; the
# fix focuses the picker control. These prove every key route lands on option 2.
_DRIVER_PICKER = r'''
import os, sys
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui
fs = tui.FullScreen("claude-code")
def worker():
    idx = tui.select("Pick one:", ["alpha", "bravo", "charlie"])
    print("PICKED:" + str(idx))
    tui.read_input("X ", "claude-code", "demo")   # keep the box alive after
fs.run(worker)
'''


@pytest.mark.parametrize("keys,expected", [
    ([b"\x1b[B", b"\r"], "PICKED:1"),   # ↓ then Enter → bravo
    ([b"j", b"\r"],      "PICKED:1"),   # j then Enter → bravo (arrow-free)
    ([b"2"],             "PICKED:1"),   # digit jump → bravo
])
def test_picker_navigates_by_arrow_jk_and_digit(keys, expected):
    raw, lines = _spawn_and_drive(keys + [b"/exit\r"], driver=_DRIVER_PICKER,
                                  settle=1.2, total_timeout=16.0)
    text = "\n".join(lines)
    assert expected in text, f"picker did not select bravo via {keys}:\n{text}"


# Token-by-token streaming (partial lines, NO trailing newline) must NOT corrupt
# the box's top rule, and the streamed text must survive (the real-terminal bug
# whole-line print() tests missed).
_DRIVER_STREAM = r'''
import os, sys, time
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui
fs = tui.FullScreen("claude-code")
def worker():
    tui.read_input("X ", "claude-code", "demo")
    for tk in "the forward model is linear and monochromatic here".split(" "):
        sys.stdout.write(tk + " "); sys.stdout.flush(); time.sleep(0.03)
    sys.stdout.write("\n")
    tui.read_input("X ", "claude-code", "demo")
fs.run(worker)
'''


def test_token_streaming_keeps_box_intact_and_content():
    raw, lines = _spawn_and_drive([b"go\r", b"/exit\r"],
                                  driver=_DRIVER_STREAM, settle=1.5,
                                  total_timeout=16.0)
    # The streamed text survived (not erased on repaint).
    text = "\n".join(lines)
    assert "monochromatic" in text, f"streamed text vanished:\n{text}"
    # No box rule has streamed words fused onto it (the corruption signature:
    # a run of '─' on the SAME line as letters).
    import re
    for ln in lines:
        if "─" in ln and re.search(r"[A-Za-z]", ln):
            # the info/status line legitimately mixes text; a RULE line is mostly
            # box-drawing — flag a line that is a rule with words welded on.
            dashes = ln.count("─")
            if dashes >= 10:
                raise AssertionError(f"box rule corrupted by stream: {ln!r}")


# A message typed WHILE the agent is busy must echo IMMEDIATELY (not vanish until
# the turn ends). This is the real "my sentence disappears after I send it" bug.
_DRIVER_BUSY = r'''
import os, sys, time
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui
fs = tui.FullScreen("claude-code")
def worker():
    tui.read_input("X ", "claude-code", "demo")
    for i in range(20):                       # ~4s of busy streaming
        sys.stdout.write("tok%d " % i); sys.stdout.flush(); time.sleep(0.2)
    sys.stdout.write("\n")
    tui.read_input("X ", "claude-code", "demo")
    tui.read_input("X ", "claude-code", "demo")
fs.run(worker)
'''


def test_message_sent_while_busy_echoes_immediately():
    # Send msg1 (starts the 4s stream), then ~1s in send msg2 while busy.
    # Snapshot must show msg2 BEFORE the stream finishes.
    import os as _os, pty, select, time as _t, pyte
    repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    pid, fd = pty.fork()
    if pid == 0:
        _os.environ["TERM"] = "xterm-256color"
        _os.environ["PYTHONPATH"] = repo + _os.pathsep + _os.environ.get("PYTHONPATH", "")
        _os.execvp("python3", ["python3", "-c", _DRIVER_BUSY])
        _os._exit(127)
    screen = pyte.Screen(80, 24); stream = pyte.ByteStream(screen)
    def pump(dl):
        while _t.monotonic() < dl:
            r, _, _ = select.select([fd], [], [], 0.1)
            if fd in r:
                try: c = _os.read(fd, 65536)
                except OSError: return
                if not c: return
                stream.feed(c)
    t0 = _t.monotonic(); pump(t0 + 1.5)
    _os.write(fd, b"start\r"); pump(_t.monotonic() + 1.0)
    _os.write(fd, b"busy message\r"); pump(_t.monotonic() + 0.8)
    mid = "\n".join(ln.rstrip() for ln in screen.display)
    # the stream is NOT done yet (token 19 not reached), yet the message shows:
    assert "busy message" in mid, f"message sent while busy vanished:\n{mid}"
    assert "tok19" not in mid, "stream finished too early; test inconclusive"
    _os.write(fd, b"/exit\r"); pump(_t.monotonic() + 5.0)
    try: _os.close(fd)
    except OSError: pass
    try: _os.waitpid(pid, 0)
    except OSError: pass


# Permission picker: ↑/↓ move the highlight, ⏎ selects (Claude Code parity).
_DRIVER_PICK = r'''
import os, sys
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui
fs = tui.FullScreen("claude-code")
def worker():
    tui.read_input("X ", "claude-code", "demo")
    opts = ["Yes", "Yes, and don't ask again for bash this session",
            "No, and tell the agent what to do differently (esc)"]
    idx = tui.ask_choice("DECIDE NOW", opts, mode="claude-code")
    print("CHOSE-IDX:%d" % idx)
    tui.read_input("X ", "claude-code", "demo")
fs.run(worker)
'''


def test_permission_picker_arrow_keys():
    # open the picker, Down twice (→ No), Up once (→ "don't ask again"), Enter.
    raw, lines = _spawn_and_drive(
        [b"go\r", b"\x1b[B", b"\x1b[B", b"\x1b[A", b"\r", b"/exit\r"],
        driver=_DRIVER_PICK, settle=0.8, total_timeout=14.0)
    text = "\n".join(lines)
    assert b"DECIDE NOW" in raw                        # the picker rendered
    assert "CHOSE-IDX:1" in text, f"arrow selection wrong:\n{text}"


def test_permission_picker_number_jump():
    # press '3' to jump straight to (and confirm) option 3 (index 2 = No).
    raw, lines = _spawn_and_drive(
        [b"go\r", b"3", b"/exit\r"],
        driver=_DRIVER_PICK, settle=0.8, total_timeout=14.0)
    assert "CHOSE-IDX:2" in "\n".join(lines)


# The box must NOT bounce row-by-row while a line streams token-by-token (the
# "moves up so fast" complaint): the live region is a single fixed row showing
# the tail, so the box position is stable until a line actually commits.
_DRIVER_NOBOUNCE = r'''
import os, sys, time
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui
fs = tui.FullScreen("claude-code")
def worker():
    tui.read_input("X ", "claude-code", "demo")
    # one long line (NO newline) that wraps several times as it streams
    for w in (("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda "
               "mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega ") * 2
              ).split(" "):
        if w:
            sys.stdout.write(w + " "); sys.stdout.flush(); time.sleep(0.05)
    sys.stdout.write("\n")
    tui.read_input("X ", "claude-code", "demo")
fs.run(worker)
'''


def test_box_does_not_bounce_during_token_stream():
    import os as _os, pty, select, time as _t, pyte
    repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    pid, fd = pty.fork()
    if pid == 0:
        _os.environ["TERM"] = "xterm-256color"
        _os.environ["PYTHONPATH"] = repo + _os.pathsep + _os.environ.get("PYTHONPATH", "")
        _os.execvp("python3", ["python3", "-c", _DRIVER_NOBOUNCE])
        _os._exit(127)
    screen = pyte.Screen(80, 24); stream = pyte.ByteStream(screen)
    def pump(dl):
        while _t.monotonic() < dl:
            r, _, _ = select.select([fd], [], [], 0.05)
            if fd in r:
                try: c = _os.read(fd, 65536)
                except OSError: return
                if not c: return
                stream.feed(c)
    def first_rule():
        for i, ln in enumerate(screen.display):
            if ln.rstrip().startswith("──"):
                return i
        return -1
    t0 = _t.monotonic(); pump(t0 + 1.5)
    _os.write(fd, b"go\r"); pump(_t.monotonic() + 0.6)
    rows = []
    for _ in range(4):                      # sample mid-stream (within one line)
        pump(_t.monotonic() + 0.35)
        rows.append(first_rule())
    _os.write(fd, b"/exit\r"); pump(_t.monotonic() + 4.0)
    try: _os.close(fd)
    except OSError: pass
    try: _os.waitpid(pid, 0)
    except OSError: pass
    # All samples are mid-line (no newline committed yet) → the box must not move.
    assert len(set(rows)) == 1, f"box bounced while streaming one line: rows={rows}"


def test_busy_message_is_queued_not_interleaved():
    # A message sent during work shows as "(queued)" above the box (stable), and
    # is NOT committed into the middle of the current turn's streaming output.
    import os as _os, pty, select, time as _t, pyte
    repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    pid, fd = pty.fork()
    if pid == 0:
        _os.environ["TERM"] = "xterm-256color"
        _os.environ["PYTHONPATH"] = repo + _os.pathsep + _os.environ.get("PYTHONPATH", "")
        _os.execvp("python3", ["python3", "-c", _DRIVER_BUSY])
        _os._exit(127)
    screen = pyte.Screen(80, 24); stream = pyte.ByteStream(screen)
    def pump(dl):
        while _t.monotonic() < dl:
            r, _, _ = select.select([fd], [], [], 0.1)
            if fd in r:
                try: c = _os.read(fd, 65536)
                except OSError: return
                if not c: return
                stream.feed(c)
    t0 = _t.monotonic(); pump(t0 + 1.5)
    _os.write(fd, b"start\r"); pump(_t.monotonic() + 1.0)
    _os.write(fd, b"queued one\r"); pump(_t.monotonic() + 0.8)
    mid = [ln.rstrip() for ln in screen.display]
    midtext = "\n".join(mid)
    assert "queued one" in midtext and "(queued)" in midtext, \
        f"message not shown as queued:\n{midtext}"
    assert "tok19" not in midtext, "stream finished too early; inconclusive"
    # The queued line must be BELOW the streamed tokens (just above the box),
    # not interleaved into them.
    tok_rows = [i for i, ln in enumerate(mid) if ln.startswith("tok")]
    q_rows = [i for i, ln in enumerate(mid) if "(queued)" in ln]
    assert tok_rows and q_rows and q_rows[0] > max(tok_rows), \
        f"queued message interleaved into output:\n{midtext}"
    _os.write(fd, b"/exit\r"); pump(_t.monotonic() + 5.0)
    try: _os.close(fd)
    except OSError: pass
    try: _os.waitpid(pid, 0)
    except OSError: pass


# Live "shining" status: gerund + elapsed + ↓ tokens + activity (Claude-Code feel).
_DRIVER_STATUS = r'''
import os, time
os.environ["AI4SCIENCE_TUI"] = "full"
os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
from ai4science.harness import tui
fs = tui.FullScreen("unified-LLM")
def worker():
    tui.read_input("X ", "unified-LLM", "")
    tui.begin_turn()
    tui.set_activity("running grep")
    for i in range(1, 6):
        tui.set_tokens(i * 400); time.sleep(0.3)
    time.sleep(0.4)
    tui.end_turn()
    tui.read_input("X ", "unified-LLM", "")
fs.run(worker)
'''


def test_shining_status_shows_tokens_and_activity():
    import os as _os, pty, select, time as _t, pyte
    repo = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    pid, fd = pty.fork()
    if pid == 0:
        _os.environ["TERM"] = "xterm-256color"
        _os.environ["PYTHONPATH"] = repo + _os.pathsep + _os.environ.get("PYTHONPATH", "")
        _os.execvp("python3", ["python3", "-c", _DRIVER_STATUS])
        _os._exit(127)
    sc = pyte.Screen(110, 16); st = pyte.ByteStream(sc)
    def pump(dl):
        while _t.monotonic() < dl:
            r, _, _ = select.select([fd], [], [], 0.1)
            if fd in r:
                try: c = _os.read(fd, 65536)
                except OSError: return
                if not c: return
                st.feed(c)
    t0 = _t.monotonic(); pump(t0 + 1.2)
    _os.write(fd, b"go\r"); pump(_t.monotonic() + 1.4)
    mid = "\n".join(ln.rstrip() for ln in sc.display)
    _os.write(fd, b"/exit\r"); pump(_t.monotonic() + 3.0)
    try: _os.close(fd)
    except OSError: pass
    try: _os.waitpid(pid, 0)
    except OSError: pass
    assert "tokens" in mid and "running grep" in mid, f"status missing:\n{mid}"
    assert "esc to stop" in mid

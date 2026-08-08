"""The tmux hand-off, demonstrated — the one gap piece 2 left open.

The ledger's honest note: the live test ran INSIDE tmux and hit the nesting
guard, so what had been shown was that a *failed* attach is handled — never
that the hand-off works. A PTY is a plain terminal: no TMUX in the
environment, a real tmux server, a real `attach`, a real `C-b d` detach, and
the assertion is the function RETURNED and said so. `run` is not injected —
injecting it is the unit test that already exists; this is the other half.
"""
import os
import pty
import select
import shutil
import subprocess
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(shutil.which("tmux") is None,
                                reason="no tmux on this machine")

_DRIVER = r'''
import os
os.environ.pop("TMUX", None)          # a plain terminal, not a nested one
from ai4science.harness import repl
print("RESULT:" + repl._attach_tmux(os.environ["ATTACH_TARGET"]), flush=True)
'''


def _pump(fd, raw, deadline):
    while time.monotonic() < deadline:
        r, _, _ = select.select([fd], [], [], 0.1)
        if fd in r:
            try:
                chunk = os.read(fd, 65536)
            except OSError:
                return
            if not chunk:
                return
            raw.extend(chunk)


def test_attach_takes_the_terminal_and_detach_hands_it_back():
    name = f"attach-demo-{uuid.uuid4().hex[:6]}"
    marker = f"MARKER-{name}"
    subprocess.run(["tmux", "new-session", "-d", "-s", name,
                    f"echo {marker}; sleep 60"], check=True)
    try:
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pid, fd = pty.fork()
        if pid == 0:  # child — the plain terminal
            os.environ.pop("TMUX", None)
            os.environ["ATTACH_TARGET"] = name
            os.environ["TERM"] = "xterm-256color"
            os.environ["PYTHONPATH"] = (repo + os.pathsep
                                        + os.environ.get("PYTHONPATH", ""))
            os.execvp("python3", ["python3", "-c", _DRIVER])
            os._exit(127)  # unreachable

        raw = bytearray()
        # The attach must actually take the terminal: the session's own
        # output reaches the PTY before anything is typed.
        _pump(fd, raw, time.monotonic() + 4.0)
        assert marker.encode() in raw, (
            "attach never took the terminal:\n" + raw.decode(errors="replace"))
        assert b"RESULT:" not in raw, "returned before anyone detached"

        os.write(fd, b"\x02d")               # C-b d — the owner detaches
        _pump(fd, raw, time.monotonic() + 4.0)
        os.close(fd)
        os.waitpid(pid, 0)

        text = raw.decode(errors="replace")
        assert f"RESULT:back from {name}." in text, (
            "detach did not hand the terminal back:\n" + text)
    finally:
        subprocess.run(["tmux", "kill-session", "-t", name],
                       stderr=subprocess.DEVNULL)

"""↑ edits a queued message: _pull_last_queued takes the most-recent pending
message off BOTH the display list and the worker input queue."""
import queue, threading
from ai4science.harness import tui


def _screen():
    cls = next(v for v in vars(tui).values()
               if isinstance(v, type) and hasattr(v, "_pull_last_queued"))
    o = cls.__new__(cls)
    o._queued = []
    o._qlock = threading.Lock()
    o._inq = queue.Queue()
    o._invalidate = lambda: None
    return o


def _send(o, msg):                      # mimic Enter: queue display + worker input
    o._queued.append(msg)
    o._inq.put(msg)


def _drain(o):
    out = []
    try:
        while True:
            out.append(o._inq.get_nowait())
    except queue.Empty:
        pass
    return out


def test_pull_last_queued_removes_from_both():
    o = _screen()
    _send(o, "first"); _send(o, "second")
    assert o._pull_last_queued() == "second"
    assert o._queued == ["first"]
    assert _drain(o) == ["first"]       # worker won't process the edited one


def test_pull_last_queued_empty_returns_none():
    o = _screen()
    assert o._pull_last_queued() is None


def test_pull_preserves_order_with_three():
    o = _screen()
    for m in ("a", "b", "c"):
        _send(o, m)
    assert o._pull_last_queued() == "c"
    assert o._queued == ["a", "b"]
    assert _drain(o) == ["a", "b"]      # FIFO order preserved


def test_pull_ignores_sentinel_none_in_queue():
    o = _screen()
    _send(o, "real"); o._inq.put(None)   # a None (exit sentinel) after a real msg
    assert o._pull_last_queued() == "real"
    assert _drain(o) == [None]           # the sentinel survives; the message left

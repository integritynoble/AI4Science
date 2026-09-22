"""The evaluator child: ``python -m ai4science.harness.runtime.isolated_eval.evaluator SPEC``.

It is launched by :mod:`.runner` with its own cwd, a scrubbed environment and no
inherited file descriptors it did not ask for. It reads the run through the
sealed handoff snapshot, never the agent's live tree, and writes its verdict into
a store the agent cannot open. One line of JSON on stdout is the receipt.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

from .errors import BoundaryViolation, NetworkDenied, TamperDetected
from .handoff import Handoff, verify_handoff
from .store import EvaluatorStore


def deny_network() -> None:
    """Take the network away from this process before any scorer is imported.

    The evaluator scores what is in front of it. If it can call out, a scorer can
    be told what to say, or can carry the score somewhere the optimizer reads it.
    """
    import socket

    def _refuse(*_a, **_k):
        raise NetworkDenied("the evaluator has no network; socket attempt refused")

    class _NoSocket:
        def __init__(self, *_a, **_k):
            _refuse()

    socket.socket = _NoSocket                  # type: ignore[assignment]
    socket.create_connection = _refuse         # type: ignore[assignment]
    socket.create_server = _refuse             # type: ignore[assignment]
    socket.getaddrinfo = _refuse               # type: ignore[assignment]
    socket.gethostbyname = _refuse             # type: ignore[assignment]


def check_boundary(spec: dict) -> None:
    """Refuse to score at all if the agent's world is reachable from in here."""
    agent_root = Path(spec["agent_root"]).resolve()
    workdir = Path(spec["workdir"]).resolve()
    cwd = Path.cwd().resolve()

    if cwd != workdir:
        raise BoundaryViolation(f"evaluator cwd is {cwd}, not its own workdir {workdir}")
    if cwd == agent_root or agent_root in cwd.parents:
        raise BoundaryViolation(f"evaluator cwd {cwd} is inside the agent's tree {agent_root}")
    for entry in sys.path:
        if not entry:
            continue
        p = Path(entry).resolve()
        if p == agent_root or agent_root in p.parents:
            raise BoundaryViolation(f"agent tree {agent_root} is on sys.path as {entry}")
    for name, value in os.environ.items():
        if name in {"PWD", "HOME", "TMPDIR"}:
            continue
        if str(agent_root) in value:
            raise BoundaryViolation(f"environment carries the agent's tree: {name}={value}")


def load_scorer(dotted: str):
    module_name, _, attr = dotted.partition(":")
    if not attr:
        raise ValueError(f"scorer {dotted!r} must be 'module:function'")
    return getattr(importlib.import_module(module_name), attr)


def evaluate(spec: dict) -> dict:
    """Score one handed-over run. Returns the verdict payload (no timestamps: the
    same run scored twice must seal to the same digest)."""
    run_id = spec["run_id"]
    store = EvaluatorStore(Path(spec["store"]))

    def refuse(kind: str, detail: str) -> dict:
        store.record_incident(run_id, kind, detail)
        return {"run_id": run_id, "decision": "refused", "score": 0.0,
                "scorer": spec["scorer"], "criteria": spec.get("criteria", {}),
                "handoff_digest": spec.get("handoff_digest"),
                "incident": {"kind": kind, "detail": detail}, "feedback": {}}

    try:
        check_boundary(spec)
    except BoundaryViolation as exc:
        return refuse("boundary_violation", str(exc))

    try:
        handoff = Handoff.from_dict(store.get_handoff(run_id))
        verify_handoff(handoff)
    except TamperDetected as exc:
        store.record_incident(run_id, exc.kind, exc.detail)
        return {"run_id": run_id, "decision": "tampered", "score": 0.0,
                "scorer": spec["scorer"], "criteria": spec.get("criteria", {}),
                "handoff_digest": spec.get("handoff_digest"),
                "incident": {"kind": exc.kind, "detail": exc.detail}, "feedback": {}}

    try:
        scorer = load_scorer(spec["scorer"])
        result = scorer(handoff.root, spec.get("criteria", {}))
    except NetworkDenied as exc:
        return refuse("network_attempt_refused", f"{spec['scorer']}: {exc}")

    return {"run_id": run_id,
            "decision": result.get("decision", "needs_review"),
            "score": float(result.get("score", 0.0)),
            "scorer": spec["scorer"],
            "criteria": spec.get("criteria", {}),
            "handoff_digest": handoff.digest,
            "incident": None,
            "feedback": result.get("feedback", {})}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python -m ...isolated_eval.evaluator SPEC_JSON_PATH", file=sys.stderr)
        return 2
    deny_network()
    spec = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    payload = evaluate(spec)
    store = EvaluatorStore(Path(spec["store"]))
    digest = store.put_verdict(spec["run_id"], payload)
    print(json.dumps({"run_id": spec["run_id"], "decision": payload["decision"],
                      "verdict_digest": digest, "pid": os.getpid(),
                      "cwd": os.getcwd()}, sort_keys=True))
    return 0


if __name__ == "__main__":   # pragma: no cover - exercised as a child process
    raise SystemExit(main())

"""Phase 5 isolation: the evaluator runs outside the agent's world, and every
attempt to reach past the boundary is caught and named.

The six checks the phase asks for are the six test names below. Everything else
here is scaffolding for them.
"""

from __future__ import annotations

import json
import os
import textwrap

import pytest

from ai4science.harness.runtime.isolated_eval import (
    EvaluatorStore, IsolatedEvaluator, IsolatedEvaluatorVerifier, TamperDetected)
from ai4science.harness.runtime.contract import compile_contract

RUN = "run-0001"

_PROBE_SCORERS = textwrap.dedent('''
    """Scorers used only by the isolation tests. They live outside the agent tree."""
    import os
    import socket


    def where_am_i(handoff_root, criteria):
        return {"decision": "pass", "score": 1.0,
                "feedback": {"pid": os.getpid(), "cwd": os.getcwd(),
                             "path": os.environ.get("PATH"),
                             "sys_path_has_agent": any(
                                 str(criteria["agent_root"]) in p for p in __import__("sys").path)}}


    def reach_for_the_network(handoff_root, criteria):
        socket.create_connection(("127.0.0.1", 9), timeout=0.1)
        return {"decision": "pass", "score": 1.0, "feedback": {"reached": True}}


    def open_a_listening_socket(handoff_root, criteria):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        return {"decision": "pass", "score": 1.0, "feedback": {"reached": True}}
''')


@pytest.fixture
def world(tmp_path):
    """An agent workspace with a run in it, and an evaluator rooted elsewhere."""
    agent = tmp_path / "agent" / "workspace"
    agent.mkdir(parents=True)
    (agent / "result.json").write_text(json.dumps({"psnr": 31.4}), encoding="utf-8")
    (agent / "solver.py").write_text("# the agent's work\n", encoding="utf-8")

    scorers = tmp_path / "evaluator-scorers"
    scorers.mkdir()
    (scorers / "probe_scorers.py").write_text(_PROBE_SCORERS, encoding="utf-8")

    def make(**kw):
        kw.setdefault("criteria", {"required_artifacts": ["result.json", "solver.py"]})
        return IsolatedEvaluator(root=tmp_path / "evaluator", agent_workspace=agent,
                                 scorer_path=scorers, **kw)

    return {"agent": agent, "scorers": scorers, "make": make, "tmp": tmp_path}


def _as_attacker(store_root):
    """The agent wins the race and gets the directory open. Layer 2 is what is
    on trial in the tests that use this, so we grant layer 1 rather than pretend."""
    os.chmod(store_root, 0o700)


# -- the six checks -----------------------------------------------------------


def test_the_evaluator_runs_in_a_separate_process_with_a_different_cwd(world):
    ev = world["make"](scorer="probe_scorers:where_am_i",
                       criteria={"agent_root": str(world["agent"])})
    out = ev.evaluate(RUN)

    receipt = out["receipt"]
    assert receipt["pid"] != os.getpid(), "the evaluator shared the agent's process"
    assert receipt["cwd"] != os.getcwd()
    assert receipt["cwd"] != str(world["agent"])
    assert receipt["cwd"] == str((world["tmp"] / "evaluator" / "work").resolve())

    feedback = out["verdict"]["feedback"]
    assert feedback["pid"] == receipt["pid"]
    # no agent tools on the child's PATH, and the agent's tree is not importable
    assert feedback["path"] == "/usr/bin:/bin"
    assert feedback["sys_path_has_agent"] is False


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits it set")
def test_the_agent_cannot_open_the_evaluators_store(world):
    ev = world["make"]()
    ev.evaluate(RUN)

    store_root = (world["tmp"] / "evaluator" / "store")
    assert (store_root.stat().st_mode & 0o777) == 0o000, "the store was left open"

    with pytest.raises(PermissionError):
        (store_root / "verdicts" / f"{RUN}.json").read_text()
    with pytest.raises(PermissionError):
        list(store_root.iterdir())
    with pytest.raises(PermissionError):
        (store_root / "seal.key").read_bytes()

    # reaching for it through the one handle the agent is given is refused by name
    with pytest.raises(PermissionError):
        ev.verdict_view.open_store(store_root / "verdicts")
    assert [i["kind"] for i in ev.incidents()] == ["store_access_refused"]

    # and the sanctioned read still works, without handing over a path
    assert ev.verdict_view.decision(RUN) == "pass"
    assert "store" not in repr(ev.verdict_view)


def test_artefacts_edited_after_handoff_are_detected_by_hash(world):
    ev = world["make"]()
    ev.hand_over(RUN)

    snapshot = world["tmp"] / "evaluator" / "handoff" / RUN / "result.json"
    os.chmod(snapshot, 0o644)
    snapshot.write_text(json.dumps({"psnr": 99.9}), encoding="utf-8")

    out = ev.evaluate(RUN, hand_over=False)
    assert out["verdict"]["decision"] == "tampered"
    incident = out["verdict"]["incident"]
    assert incident["kind"] == "artefact_edited_after_handoff"
    assert "result.json" in incident["detail"]
    assert ev.incidents(RUN)[-1]["kind"] == "artefact_edited_after_handoff"


def test_artefacts_added_or_removed_after_handoff_are_named_too(world):
    ev = world["make"]()
    ev.hand_over(RUN)
    (world["tmp"] / "evaluator" / "handoff" / RUN / "extra.json").write_text("{}", encoding="utf-8")

    out = ev.evaluate(RUN, hand_over=False)
    assert out["verdict"]["incident"]["kind"] == "artefact_added_after_handoff"


def test_a_verdict_edited_after_it_is_written_is_detected(world):
    ev = world["make"](criteria={"required_artifacts": ["result.json", "missing.npy"]})
    out = ev.evaluate(RUN)
    assert out["verdict"]["decision"] == "fail"

    store_root = world["tmp"] / "evaluator" / "store"
    _as_attacker(store_root)
    path = store_root / "verdicts" / f"{RUN}.json"
    blob = json.loads(path.read_text(encoding="utf-8"))
    blob["payload"]["decision"] = "pass"          # the optimizer improves its score
    blob["payload"]["score"] = 1.0
    path.write_text(json.dumps(blob, sort_keys=True), encoding="utf-8")

    with pytest.raises(TamperDetected) as exc:
        ev.read_verdict(RUN)
    assert exc.value.kind == "verdict_seal_broken"
    assert RUN in exc.value.detail
    assert ev.incidents(RUN)[-1]["kind"] == "verdict_seal_broken"


def test_the_evaluator_has_no_network_a_socket_attempt_is_refused(world):
    ev = world["make"](scorer="probe_scorers:reach_for_the_network")
    out = ev.evaluate(RUN)
    assert out["verdict"]["decision"] == "refused"
    assert out["verdict"]["incident"]["kind"] == "network_attempt_refused"
    assert "no network" in out["verdict"]["incident"]["detail"]

    listener = world["make"](scorer="probe_scorers:open_a_listening_socket")
    assert listener.evaluate("run-0002")["verdict"]["decision"] == "refused"


def test_the_same_run_evaluated_twice_yields_the_same_verdict(world):
    ev = world["make"]()
    first = ev.evaluate(RUN)
    second = ev.evaluate(RUN)

    assert first["verdict_digest"] == second["verdict_digest"]
    assert first["verdict"] == second["verdict"]
    assert first["receipt"]["pid"] != second["receipt"]["pid"], "same process twice"
    # the digest is the whole point: a diff between two evaluations means tampering
    assert first["verdict_digest"] == EvaluatorStore.digest_of(second["verdict"])


# -- it has to be usable, not just safe ---------------------------------------


def test_the_verifier_drops_into_the_plan_execute_verify_loop(world):
    ev = world["make"]()
    contract = compile_contract(objective="score a run", capability_profile="A1")

    verdict = IsolatedEvaluatorVerifier(ev, RUN).check({"exit_code": 0}, contract)
    assert verdict.complete is True and verdict.repairable is False
    assert verdict.evidence["decision"] == "pass"
    assert verdict.evidence["verdict_digest"].startswith("sha256:")

    missing = world["make"](criteria={"required_artifacts": ["nope.npy"]})
    failed = IsolatedEvaluatorVerifier(missing, "run-0003").check({"exit_code": 0}, contract)
    assert failed.complete is False and failed.repairable is True
    assert failed.evidence["feedback"]["missing"] == ["nope.npy"]


def test_a_tampered_run_is_unverifiable_not_merely_failed(world):
    """A failed run is repairable; a tampered one is not. The loop must not offer
    the optimizer another go at a boundary it just tried to cross."""
    ev = world["make"]()
    contract = compile_contract(objective="score a run", capability_profile="A1")
    ev.hand_over(RUN)

    snapshot = world["tmp"] / "evaluator" / "handoff" / RUN / "solver.py"
    os.chmod(snapshot, 0o644)
    snapshot.write_text("# edited after the handoff\n", encoding="utf-8")

    verifier = IsolatedEvaluatorVerifier(ev, RUN, hand_over=False)
    verdict = verifier.check({"exit_code": 0}, contract)
    assert verdict.complete is False and verdict.repairable is False
    assert verdict.evidence["decision"] == "tampered"
    assert verdict.evidence["incident"]["kind"] == "artefact_edited_after_handoff"


def test_a_verdict_that_does_not_match_its_receipt_is_caught_on_the_way_out(world, monkeypatch):
    """Between the child sealing a verdict and the harness reading it, the store
    is the only thing standing there. If what comes back is not what was sealed,
    the harness says so instead of scoring it."""
    ev = world["make"]()
    monkeypatch.setattr(type(ev), "read_verdict",
                        lambda self, run_id: {"run_id": run_id, "decision": "pass",
                                              "score": 1.0, "feedback": {}})
    with pytest.raises(TamperDetected) as exc:
        ev.evaluate(RUN)
    assert exc.value.kind == "verdict_seal_broken"
    assert "receipted" in exc.value.detail


def test_the_handoff_is_a_snapshot_not_the_agents_live_tree(world):
    ev = world["make"]()
    handoff = ev.hand_over(RUN)
    assert handoff["root"] != str(world["agent"])
    for rel in handoff["files"]:
        snap = world["tmp"] / "evaluator" / "handoff" / RUN / rel
        assert snap.exists() and (snap.stat().st_mode & 0o222) == 0, f"{rel} is writable"


def test_the_evaluator_refuses_to_load_its_own_code_from_the_agents_tree(world, tmp_path):
    import ai4science
    from pathlib import Path
    from ai4science.harness.runtime.isolated_eval import BoundaryViolation

    code_root = Path(ai4science.__file__).resolve().parent.parent
    with pytest.raises(BoundaryViolation):
        IsolatedEvaluator(root=tmp_path / "ev2", agent_workspace=code_root)

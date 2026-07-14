from ai4science.harness.agents.machine.policy import OperationPolicy, incumbent_operation_policy
from ai4science.harness.agents.machine.rsi_search import score_routing, run_machine_rsi_search
from ai4science.harness.agents.machine.bench import TRAIN_CASES, VAL_CASES
from ai4science.harness.agents.machine.operations import default_operations
from ai4science.harness.agents.machine.agent import run_machine


def test_incumbent_baseline_and_safety():
    s = score_routing(incumbent_operation_policy(), VAL_CASES)
    assert s["safety_ok"] is True          # incumbent never routes a gap to an op
    assert s["accuracy"] < 1.0             # ...but misses some paraphrases


def test_search_improves_val_and_adopts():
    out = run_machine_rsi_search()
    assert out["safety_ok"] is True
    assert out["val_accuracy"] > out["incumbent_val_accuracy"]
    assert out["adopt"] is True


def test_does_not_overfit_to_100():
    assert run_machine_rsi_search()["val_accuracy"] < 1.0


def test_gaps_never_become_operations():
    out = run_machine_rsi_search()
    best = OperationPolicy(out["best_policy"])
    for c in TRAIN_CASES + VAL_CASES:
        if c["expected"] is None:
            assert best.select(c["intent"], default_operations()) is None, c["intent"]


def test_routing_policy_cannot_cause_unapproved_action():
    # even an adversarial policy that routes "delete files" to install cannot run
    # it: run_machine gates the consequential op with approve() downstream.
    evil = OperationPolicy({"install_claude_code": ("delete", "format", "wipe")})
    out = run_machine(intent="format the hard drive", caps={"os": "linux", "installed": {}, "supported": True},
                      approve=lambda op, ctx: False, select=evil.select,
                      execute=lambda o, c: (_ for _ in ()).throw(AssertionError("must not run")))
    assert out["status"] == "needs_approval"    # gated, not executed


def test_search_is_deterministic():
    a = run_machine_rsi_search()
    b = run_machine_rsi_search()
    assert a["best_policy"] == b["best_policy"] and a["adopt"] == b["adopt"]

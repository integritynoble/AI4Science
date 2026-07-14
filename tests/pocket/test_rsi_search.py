from ai4science.harness.agents.pocket.policy import (
    KeywordPolicy, incumbent_policy,
)
from ai4science.harness.agents.pocket.rsi_search import (
    score_policy, run_pocket_rsi_search, _outcome,
)
from ai4science.harness.agents.pocket.bench import TRAIN_CASES, VAL_CASES
from ai4science.harness.agents.pocket.agent import run_pocket
from ai4science.harness.agents.pocket.tools import default_registry


def test_incumbent_policy_reproduces_shipped_behavior():
    inc = incumbent_policy()
    # incumbent map == the registry's Tool.match, verbatim
    assert inc.as_map() == {t.name: t.match for t in default_registry()}
    # and selecting through it matches run_pocket's default keyword selection
    for intent in ("remind me to call mom", "what's on my calendar", "take a memo"):
        via_policy = run_pocket(intent=intent, granted=("reminders", "calendar", "notes"),
                                select=inc.select, ctx={})
        default = run_pocket(intent=intent, granted=("reminders", "calendar", "notes"), ctx={})
        assert _outcome(via_policy) == _outcome(default)


def test_incumbent_val_baseline_pinned():
    s = score_policy(incumbent_policy(), VAL_CASES)
    assert s["accuracy"] == 0.6          # 6/10 held-out cases routed correctly
    assert s["autonomy"] == 0.3          # 3/10 resolved to a direct tool action
    assert s["safety_ok"] is True


def test_search_improves_val_and_recommends_adopt():
    out = run_pocket_rsi_search()
    assert out["safety_ok"] is True
    assert out["val_accuracy"] > out["incumbent_val_accuracy"]
    assert out["val_autonomy"] > out["incumbent_val_autonomy"]
    assert out["adopt"] is True
    assert out["val_accuracy"] == 0.9    # learns memo / task / free; 9/10
    # learned exactly the tokens we expect to matter
    learned = out["learned"]
    assert "memo" in learned.get("note_write", ())
    assert "task" in learned.get("reminder_create", ())
    assert "free" in learned.get("calendar_read", ())


def test_does_not_overfit_to_100_percent():
    # the held-out "put milk on my list" has no train-taught token -> stays unsolved
    out = run_pocket_rsi_search()
    assert out["val_accuracy"] < 1.0


def test_safety_is_downstream_of_the_gate():
    # an ADVERSARIAL policy that maps a spend phrase to a benign tool must STILL
    # hand off — the risk ceiling runs before select, so no policy can under-refuse.
    evil = KeywordPolicy({"note_write": ("pay", "transfer", "publish")})
    out = run_pocket(intent="pay $30 to the landlord",
                     granted=("notes",), select=evil.select, ctx={})
    assert out["status"] == "handoff" and out["kind"] == "spend"


def test_best_policy_safety_ok_on_both_splits():
    out = run_pocket_rsi_search()
    best = KeywordPolicy(out["best_policy"])
    assert score_policy(best, TRAIN_CASES)["safety_ok"] is True
    assert score_policy(best, VAL_CASES)["safety_ok"] is True
    # every consequential case still hands off under the learned policy
    for c in VAL_CASES:
        if tuple(c["expected"])[0] == "handoff":
            out2 = run_pocket(intent=c["intent"], granted=c["granted"],
                              select=best.select, ctx={})
            assert out2["status"] == "handoff"


def test_no_regression_on_incumbent_hits():
    out = run_pocket_rsi_search()
    best = KeywordPolicy(out["best_policy"])
    inc = incumbent_policy()
    for c in VAL_CASES:
        inc_out = _outcome(run_pocket(intent=c["intent"], granted=c["granted"],
                                      select=inc.select, ctx={}))
        if inc_out == tuple(c["expected"]):   # incumbent already right
            best_out = _outcome(run_pocket(intent=c["intent"], granted=c["granted"],
                                           select=best.select, ctx={}))
            assert best_out == tuple(c["expected"]), f"regressed: {c['intent']}"


def test_search_is_deterministic():
    a = run_pocket_rsi_search()
    b = run_pocket_rsi_search()
    assert a["best_policy"] == b["best_policy"]
    assert a["learned"] == b["learned"]
    assert a["val_accuracy"] == b["val_accuracy"]
    assert a["adopt"] == b["adopt"]


def test_returns_recommendation_not_action():
    # the loop mutates no default: the shipped registry keywords are unchanged
    before = {t.name: t.match for t in default_registry()}
    run_pocket_rsi_search()
    after = {t.name: t.match for t in default_registry()}
    assert before == after

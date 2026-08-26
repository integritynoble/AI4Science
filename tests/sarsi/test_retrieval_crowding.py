"""A lesson that falls out of its own retrieval slice as the store grows.

Found by the M5.5 memory ablation (2026-08-26) once the trap set went from
three classes to eleven. With fourteen active entries and the gate's `k=6`, the
`IDKEY` lesson — "account ids are unique only within a region" — did not make
the top six for its own query, and the ablation recorded `lesson in context:
False` in the arm that was supposed to have it. Six other lessons outranked it
on keyword overlap alone.

Two things were wrong, and they are separable:

  * `retrieval.retrieve` accepts a `scope=` and filters on it. `workspace_context`
    never passed one. It passed `task_id`, and the scorer's only scope signal is
    a bonus for `task:{id}` — which a lesson consolidated from EARLIER, different
    tasks can never match. So learned memory competed on keyword overlap alone,
    globally.

  * even unfiltered, an entry scoped to the same store as the query is more
    relevant than one that merely shares a word, and scored no better for it.

§6.1 says memory classes are not retrieved the same way. The protected arm
honours that; the ranked arm did not.
"""
import pytest

from ai4science.harness.agents.sarsi import (registry as reg, retrieval,
                                             selfaware as sa, semantic as sem,
                                             task as tsk, worker as wk)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["sarsi-worker"]


#: The shape the ablation hit: one lesson that answers the question, and a
#: crowd of others that share more words with it than it shares with itself.
WANTED = "account ids are unique only within a region, so the key is the pair"
QUERY = "count the distinct accounts in the April extract"

CROWD = [
    "the ledger records amounts in the account's own currency, and the April "
    "rate is applied per account",
    "the upstream April extract reports timestamps in local time, not UTC",
    "the ledger's amount column is in minor units, counted per account",
    "the April export counts distinct rows before any account is resolved",
    "the metrics extract reports latency per account in microseconds",
    "in the April scores extract, -1 means the run was not counted",
    "the audit extract lists accounts newest-first",
]


def _seed(config, agent, *, wanted_scope):
    sem.record(config, agent, WANTED, kind="lesson", status="active",
               scope=wanted_scope, promoted_by="owner")
    for c in CROWD:
        sem.record(config, agent, c, kind="lesson", status="active",
                   scope=["store:ledger"], promoted_by="owner")


def _names(got):
    return [e["statement"] for e in got["retrieved"]]


def test_the_crowd_buries_the_lesson_when_nothing_scopes_the_query(config, agent):
    """The defect, pinned. Without a scope the lesson loses on word overlap.

    Kept as a test rather than deleted with the fix: it is the reason the scope
    is passed, and a later change that stops passing it would otherwise look
    harmless."""
    _seed(config, agent, wanted_scope=["store:accounts"])

    got = retrieval.retrieve(config, agent, query=QUERY, k=6)

    assert WANTED not in _names(got), (
        "if the crowd no longer buries it, this fixture no longer reproduces "
        "the condition the fix is for")


def test_a_scoped_query_retrieves_the_lesson_for_its_own_store(config, agent):
    _seed(config, agent, wanted_scope=["store:accounts"])

    got = retrieval.retrieve(config, agent, query=QUERY,
                             scope=["store:accounts"], k=6)

    assert WANTED in _names(got)


def test_a_scope_match_is_a_ranking_signal_and_not_only_a_filter(config, agent):
    """The second half, unit-tested on the scorer.

    It cannot be tested through `retrieve`, because passing a scope there also
    FILTERS — and then any improvement in rank is indistinguishable from having
    removed the competition. The claim is narrower and worth pinning on its
    own: an entry scoped to what the query is about scores higher than the same
    entry unscoped, so the repair does not depend entirely on every caller
    getting the filter right."""
    entry = {"statement": WANTED, "scope": ["store:accounts"]}
    tokens = retrieval._tokens(QUERY)

    blind = retrieval._lexical_score(entry, tokens, task_id="", scope=None)
    aware = retrieval._lexical_score(entry, tokens, task_id="",
                                     scope=["store:accounts"])

    assert aware > blind, (blind, aware)


def test_but_global_is_not_a_scope_match(config, agent):
    """`global` matches everything, so rewarding it would rank the least
    specific entries highest — the opposite of what the signal is for."""
    entry = {"statement": WANTED, "scope": ["global"]}
    tokens = retrieval._tokens(QUERY)

    assert (retrieval._lexical_score(entry, tokens, "", scope=["global"])
            == retrieval._lexical_score(entry, tokens, "", scope=None))


def test_and_the_task_own_scope_still_outranks_a_store_scope(config, agent):
    """A lesson about THIS task is stronger evidence than one about the store
    it belongs to, and the two signals must not be worth the same."""
    tokens = retrieval._tokens(QUERY)
    mine = {"statement": WANTED, "scope": ["task:tsk_abc"]}
    store = {"statement": WANTED, "scope": ["store:accounts"]}

    assert (retrieval._lexical_score(mine, tokens, "tsk_abc", ["store:accounts"])
            > retrieval._lexical_score(store, tokens, "tsk_abc", ["store:accounts"]))


def test_a_global_lesson_survives_any_scope(config, agent):
    """`active_entries` admits `global` whatever the filter says, and it has to:
    a constraint that applies everywhere is exactly the one a narrow scope
    would drop."""
    sem.record(config, agent, "never push to main without approval",
               kind="invariant", status="active", scope=["global"],
               promoted_by="owner")
    _seed(config, agent, wanted_scope=["store:accounts"])

    got = retrieval.retrieve(config, agent, query=QUERY,
                             scope=["store:accounts"], k=6)

    assert any("never push to main" in e["statement"] for e in got["protected"])


def test_the_gate_passes_the_standing_tasks_scope(config, agent):
    """The live path. `workspace_context` is what the ablation measured, and it
    is where the scope was missing."""
    _seed(config, agent, wanted_scope=["store:accounts"])
    d = wk.Directive(agent_id=agent.id, goal=QUERY, scope=["store:accounts"])
    t = tsk.create(config, agent, d)
    from ai4science.harness.agents.sarsi import chat
    chat._stand(config, agent, t.id, "cli")

    ctx = sa.workspace_context(config, agent, observation=QUERY,
                               mode="REASON", snapshot=False)

    assert WANTED in ctx


def test_and_a_task_with_no_declared_scope_narrows_nothing(config, agent):
    """No scope must mean no filter, never an empty one. A task that declares
    nothing should see what it saw before — silently narrowing it would be the
    same defect pointing the other way."""
    _seed(config, agent, wanted_scope=["store:accounts"])
    t = tsk.create(config, agent, wk.Directive(agent_id=agent.id, goal=QUERY))
    from ai4science.harness.agents.sarsi import chat
    chat._stand(config, agent, t.id, "cli")

    ctx = sa.workspace_context(config, agent, observation=QUERY,
                               mode="REASON", snapshot=False)

    assert any(c[:40] in ctx for c in CROWD), "the unscoped view is unchanged"


# ── what applies is a different question from what is related ──────────────

CURRENCY_Q = "what is the total of the April ledger in USD?"
CURRENCY_LESSON = "amounts are in the account's own currency; EU is EUR at 1.10"
UNITS_LESSON = "the ledger's amount column is in minor units (cents)"


def _ledger(config, agent):
    for stmt in (CURRENCY_LESSON, UNITS_LESSON):
        sem.record(config, agent, stmt, kind="lesson", status="active",
                   scope=["store:ledger"], promoted_by="owner")
    return retrieval.retrieve(config, agent, query=CURRENCY_Q,
                              scope=["store:ledger"], k=6)["retrieved"]


def test_a_true_lesson_about_another_question_can_be_dropped(config, agent):
    """The defect this exists for. Both lessons are true, both are about the
    ledger, and one of them is not about the question — so ranking and filters
    both admit it. Measured: the model applied both and answered 2.10 instead
    of 210.00, five times out of five."""
    entries = _ledger(config, agent)
    assert len(entries) == 2

    def judge(prompt):
        assert CURRENCY_Q in prompt, "the judge is asked about THIS task"
        # Keep whichever numbered line carries the currency lesson, whatever
        # order retrieval put them in — a test that hard-codes the index passes
        # for the wrong reason the day the ranking changes.
        line = next(ln for ln in prompt.splitlines() if CURRENCY_LESSON in ln)
        return f"KEEP={line.split('.')[0].strip()}"

    kept, report = retrieval.applicable(CURRENCY_Q, entries, judge=judge)

    assert [e["statement"] for e in kept] == [CURRENCY_LESSON]
    assert report["why"] == "judged" and len(report["dropped"]) == 1


@pytest.mark.parametrize("answer,why", [
    ("KEEP=ALL", "said ALL"),
    ("I am not sure", "nothing parseable"),
    ("KEEP=9", "an index that does not exist"),
    ("KEEP=", "an empty set"),
])
def test_every_uncertain_answer_keeps_everything(config, agent, answer, why):
    """The bias is measured, not chosen. Telling the reader to weigh
    applicability itself cost `UNITS` 5/5 → 2/5 and `EXCLUSIVE` 5/5 → 0/5, and
    took repeat errors from 5 to 13 in 55. Dropping a lesson that applies is
    worse than carrying one that does not, so every uncertain path keeps."""
    entries = _ledger(config, agent)

    kept, report = retrieval.applicable(CURRENCY_Q, entries,
                                        judge=lambda p: answer)

    assert len(kept) == len(entries), why
    assert not report["dropped"]


def test_a_judge_that_keeps_nothing_has_broken_not_judged(config, agent):
    """A filter that empties the context is not a strict filter."""
    entries = _ledger(config, agent)

    kept, report = retrieval.applicable(CURRENCY_Q, entries,
                                        judge=lambda p: "KEEP=")

    assert len(kept) == len(entries)


def test_a_judge_that_raises_keeps_everything(config, agent):
    entries = _ledger(config, agent)

    def boom(prompt):
        raise RuntimeError("no engine")

    kept, report = retrieval.applicable(CURRENCY_Q, entries, judge=boom)

    assert len(kept) == len(entries)
    assert "kept everything" in report["why"]


def test_without_an_engine_the_gate_is_unchanged(config, agent):
    """No engine must mean no filtering, never an empty context. On a host with
    no reachable model the gate has to behave exactly as it did before."""
    _ledger(config, agent)
    d = wk.Directive(agent_id=agent.id, goal=CURRENCY_Q, scope=["store:ledger"])
    t = tsk.create(config, agent, d)
    from ai4science.harness.agents.sarsi import chat
    chat._stand(config, agent, t.id, "cli")

    ctx = sa.workspace_context(config, agent, observation=CURRENCY_Q,
                               mode="REASON", snapshot=False)

    assert CURRENCY_LESSON in ctx and UNITS_LESSON in ctx

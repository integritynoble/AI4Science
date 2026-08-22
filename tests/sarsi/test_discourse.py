"""The recent window — what a short turn is allowed to mean. [plan v3 §5.7, §6.6]

`why?` after a discussion of hybrid retrieval must not send the word `why` to a
retriever. The referent is already two lines up. This is the cheap place to
look it up, and looking it up here is what lets an ordinary follow-up stay on
the fast path.

The window is bounded in TOKENS, not messages: ten one-word turns are free and
two that each pasted a traceback are not. What falls out of it is not deleted —
it stays in the log, and the render says how much of it is not here.
"""
import pytest

from ai4science.harness.agents.sarsi import discourse as d, log, registry as reg


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


# ── the window ───────────────────────────────────────────────────────────────

def test_an_empty_log_is_an_empty_window(agent):
    buf = d.recent(agent.agent_dir, "cli")
    assert buf.empty and buf.total == 0
    assert "none yet" in d.render(buf)


def test_the_window_is_the_newest_end_of_the_conversation(agent):
    for i in range(20):
        log.append(agent.agent_dir, "cli", f"turn {i}", f"reply {i}")
    buf = d.recent(agent.agent_dir, "cli", budget_tokens=120)
    assert buf.exchanges[-1]["in"] == "turn 19"
    assert buf.total == 20
    assert buf.omitted == 20 - len(buf.exchanges)


def test_the_budget_is_tokens_and_not_a_message_count(agent):
    """Two turns carrying a pasted traceback cost more than ten short ones."""
    for i in range(10):
        log.append(agent.agent_dir, "cli", f"ok {i}", "fine")
    short = d.recent(agent.agent_dir, "cli", budget_tokens=200)

    for i in range(2):
        log.append(agent.agent_dir, "cli", "here is the traceback: " + "x" * 4000,
                   "y" * 4000)
    long = d.recent(agent.agent_dir, "cli", budget_tokens=200)
    assert len(long.exchanges) < len(short.exchanges)


def test_what_the_window_leaves_behind_is_stated_not_implied(agent):
    for i in range(50):
        log.append(agent.agent_dir, "cli", f"turn {i} " + "x" * 300, "reply")
    buf = d.recent(agent.agent_dir, "cli", budget_tokens=500)
    text = d.render(buf)
    assert "older not in this window" in text
    assert str(buf.omitted) in text
    assert buf.log_path in text          # and where the rest of it is


def test_the_window_never_duplicates_the_whole_transcript(agent):
    for i in range(500):
        log.append(agent.agent_dir, "cli", f"turn {i} " + "x" * 100, "reply")
    buf = d.recent(agent.agent_dir, "cli")
    assert len(buf.exchanges) < 500
    assert buf.tokens <= d.DEFAULT_WINDOW_TOKENS + 200


def test_the_topic_is_the_task_the_recent_turns_were_about(agent):
    log.append(agent.agent_dir, "cli", "start it", "started", task_id="tsk_ab12")
    assert d.recent(agent.agent_dir, "cli").task_id == "tsk_ab12"


# ── telling the two kinds of short turn apart ────────────────────────────────

def test_a_bare_follow_up_is_elliptical_and_a_real_question_is_not():
    assert d.is_elliptical("why?")
    assert d.is_elliptical("continue")
    assert d.is_elliptical("do that")
    assert not d.is_elliptical("why does GAP-TV diverge on the second frame?")


def test_asking_for_more_words_is_not_asking_for_an_act():
    assert d.is_discourse_followup("why?")
    assert d.is_discourse_followup("go on")
    assert not d.is_discourse_followup("do it")
    assert not d.is_discourse_followup("run it again")


def test_an_explicit_reach_into_older_memory_is_recognised():
    assert d.asks_for_older_memory("what did we decide yesterday about embeddings?")
    assert d.asks_for_older_memory("do you remember the CASSI mask fix?")
    assert not d.asks_for_older_memory("what is a Kalman filter?")


# ── query construction ───────────────────────────────────────────────────────

def test_a_short_follow_up_is_expanded_with_its_referent():
    buf = d.Buffer(exchanges=[{"in": "how does hybrid retrieval work?",
                               "out": "it unions lexical and semantic candidates."}],
                   total=1)
    got = d.resolve("why?", buf)
    assert got.used_recent
    assert "hybrid retrieval" in got.query
    assert got.referent == "how does hybrid retrieval work?"


def test_expansion_is_for_retrieval_and_never_rewrites_what_was_asked():
    """The query may grow; the request may not. What the owner typed is what
    any answer or action contract is built from."""
    buf = d.Buffer(exchanges=[{"in": "archive tsk_ab12", "out": "archived"}],
                   total=1)
    got = d.resolve("why?", buf)
    assert got.line == "why?"
    assert got.query != got.line


def test_a_turn_with_its_own_subject_keeps_it(monkeypatch):
    buf = d.Buffer(exchanges=[{"in": "hello", "out": "hi"}], total=1,
                   task_id="tsk_ab12")
    got = d.resolve("write the GAP-TV solver", buf)
    assert not got.used_recent
    assert got.query.startswith("write the GAP-TV solver")
    assert "tsk_ab12" in got.query      # the standing topic, still attached


def test_with_no_window_the_turn_is_its_own_query():
    got = d.resolve("why?", None)
    assert got.query == "why?"
    assert not got.used_recent


# ── the estimator is named, because two of them exist ────────────────────────

def test_the_token_estimate_is_attributed():
    assert d.estimator() in ("tiktoken/cl100k_base", "bytes/3.5")
    assert d.estimate_tokens("") == 0
    assert d.estimate_tokens("hello world") > 0

"""The board's third face — a page, served from this machine only.

`sarsi tasks` in the CLI and `/tasks` in a chat already render the same records.
This is the third: an HTML page over the same source, so a task cannot look
ready in one place and blocked in another.

It is **local**. The board holds goals, criteria and verdicts — `abraham`'s are
personal — and every other part of this system refuses to let local facts leave
the machine. A page is not an exception to that, so:

  * **it binds to loopback and nothing else.** Binding `0.0.0.0` would put the
    owner's personal board on the network, which is the decision they made when
    they chose local.
  * **it is read-only.** A page that could start work would be an
    unauthenticated door into the fleet, reachable by anything on this host.
  * **no secret value and no body**, exactly as the ledger and the workspace
    refuse them: a grant is named, never read.
  * **every row carries its reason**, because `waiting` without what it waits on
    is indistinguishable from idle.
"""
import pytest

from ai4science.harness.agents.sarsi import (board, plan as pl, registry as reg,
                                             task as tsk, verifier as vf,
                                             worker)


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
    return config.agents["work"]


def _task(config, agent, goal="finish the export", *, secrets=()):
    d = worker.Directive(agent_id=agent.id, goal=goal,
                         requires_secrets=list(secrets))
    t = tsk.attach_plan(config, agent, tsk.create(config, agent, d), pl.draft(d))
    return tsk.start(config, agent, t)


# ── the same records as the other two faces ───────────────────────────

def test_a_task_appears_with_its_goal(config, agent):
    _task(config, agent, "finish the export")
    assert "finish the export" in board.render(config, agent)


def test_the_state_is_shown(config, agent):
    _task(config, agent)
    assert "running" in board.render(config, agent)


def test_a_blocked_row_says_what_it_waits_on(config, agent):
    """`waiting` without what it waits on is indistinguishable from idle."""
    _task(config, agent, "read my mail", secrets=["mail.read"])
    assert "mail.read" in board.render(config, agent)


def test_a_verdict_is_shown_with_its_reason(config, agent):
    t = _task(config, agent)
    tsk.finish(config, agent, t, verdict=vf.parse("PASS: 1,204 rows present"))
    page = board.render(config, agent)
    assert "PASS" in page and "1,204 rows" in page


def test_an_empty_board_says_so_rather_than_rendering_nothing(config, agent):
    assert "no tasks" in board.render(config, agent).lower()


def test_the_index_lists_every_worker(config):
    page = board.index(config)
    for name in ("work", "social", "funding", "jobs", "abraham"):
        assert name in page


def test_the_manager_is_not_a_board(config):
    """It holds no tasks. A page for it would be a page of nothing."""
    assert "sarsi-machine" not in board.index(config)


# ── what it must not carry ────────────────────────────────────────────

def test_no_secret_value_reaches_the_page(config, agent):
    from ai4science.harness.agents.sarsi import vault
    vault.put(config, "mail.smtp", "hunter2")
    t = _task(config, agent, "send the report", secrets=["mail.smtp"])
    t.grants = ["read secret mail.smtp"]
    tsk._touch(agent, t, __import__("time").time)
    page = board.render(config, agent)
    assert "hunter2" not in page
    assert "mail.smtp" in page          # named, so the owner knows what is held


def test_the_page_escapes_what_it_renders(config, agent):
    """A goal is the owner's text, not markup. A board that renders it as HTML
    is a board that can be made to render anything."""
    _task(config, agent, "fix <script>alert(1)</script> in the report")
    page = board.render(config, agent)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


# ── it stays on this machine ──────────────────────────────────────────

def test_it_binds_to_loopback(config):
    """Binding anything else would put a personal board on the network."""
    bound = []
    board.serve(config, port=0, serve_forever=False,
                make_server=lambda addr, handler: bound.append(addr))
    assert bound[0][0] in ("127.0.0.1", "::1")


def test_a_non_local_host_is_refused(config):
    with pytest.raises(board.NotLocal):
        board.serve(config, host="0.0.0.0", port=0, serve_forever=False,
                    make_server=lambda addr, handler: None)


def test_the_refusal_says_why(config):
    try:
        board.serve(config, host="0.0.0.0", port=0, serve_forever=False,
                    make_server=lambda addr, handler: None)
    except board.NotLocal as e:
        assert "network" in str(e).lower() or "machine" in str(e).lower()


# ── it is read-only ───────────────────────────────────────────────────

def test_it_offers_nothing_that_changes_anything(config, agent):
    """A page that could start work would be an unauthenticated door into the
    fleet, reachable by anything running on this host."""
    _task(config, agent)
    page = board.render(config, agent).lower()
    assert "<form" not in page
    assert "<button" not in page


def test_it_says_it_is_read_only(config, agent):
    _task(config, agent)
    assert "read-only" in board.render(config, agent).lower()


def test_a_request_for_an_unknown_agent_is_a_404(config):
    status, _ = board.page(config, "/ghost")
    assert status == 404


def test_the_root_path_is_the_index(config):
    status, body = board.page(config, "/")
    assert status == 200 and "work" in body

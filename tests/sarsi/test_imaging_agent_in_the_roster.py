"""The computational-imaging agent, wired into the roster the owner talks to.

The field had everything except a way to reach it: a page, a scope object, a
roster of sub-agents, an ordered problem list, a charter and a benchmark in
`research_agents/` — and no entry in `sarsi agents`, so `sarsi run
computational-imaging` had nothing to start. A research agent nobody can address
is a design document with tests.

Three things this entry has to get right, and each is a way it could be wrong:

  * **one name.** The page, the scope object, the roster object and this entry
    all say `computational-imaging`. The code's charter is `imaging` for a
    reason `registry.py` records — it had a runner before the package existed —
    and that alias is declared in one place. Two undeclared names for one field
    is how a reader ends up unable to tell whether they are looking at two
    things or one.
  * **attended, and said so.** Its spec launches `ai4science chat --mode
    computational-imaging`, which the supervision loop cannot read: the gate
    detection is tuned to Claude Code's TUI. So it is STARTED and reported as
    not drivable, rather than quietly mis-driven — which is what `drivable`
    exists to prevent.
  * **it does not take the general worker's vocabulary.** `sarsi-worker` owns
    "benchmark", "experiment", "data", "analysis". If this agent claimed them,
    every ordinary request would route into a research field, and the failure
    would look like the router being clever.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import registry as reg, session, triage


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    path = reg.config_path(root)
    path.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(path)
    c.ensure_dirs()
    return c


def _agent(config, agent_id="computational-imaging"):
    return config.agents[agent_id]


# ── it exists, and it is the field's agent ────────────────────────────

def test_the_owner_has_a_computational_imaging_agent_to_address():
    ids = [a["id"] for a in reg._ROSTER]
    assert "computational-imaging" in ids


def test_it_is_a_worker_not_a_second_manager(config):
    a = _agent(config)
    assert a.is_worker
    assert a.role == reg.WORKER_ROLE


def test_it_is_built_on_the_field_spec_that_actually_exists(config):
    """Not `claude-code` wearing the field's name. The spec decides what the
    session IS, and a generic session called `computational-imaging` would be
    the label doing the work the mode is supposed to do."""
    a = _agent(config)
    assert a.spec == "computational-imaging"
    from ai4science.harness.agents import registry as ar
    assert a.spec in ar.AGENT_REGISTRY, "the roster names a spec nobody ships"


# ── one name for the field ────────────────────────────────────────────

def test_its_id_is_the_name_the_documents_use():
    """The page, the scope object and the roster object all say this. An entry
    that said `imaging` here would make the sarsi roster the one place using the
    internal name."""
    import pathlib
    ra = pathlib.Path(__file__).resolve().parents[2] / "docs/research-agents"
    assert (ra / "computational-imaging.md").exists()
    assert (ra / "scope/computational-imaging.json").exists()
    assert (ra / "roster/computational-imaging.json").exists()


def test_and_the_charters_internal_name_is_still_reachable():
    """`imaging` is the charter's name in research_agents. The alias is declared
    in the doc checker; this asserts the thing it aliases has not moved."""
    from ai4science.harness.agents import research_agents as ra
    assert "imaging" in ra.NAMES
    assert ra.build("imaging") is not None


# ── attended, and honest about it ─────────────────────────────────────

def test_the_supervision_loop_does_not_claim_to_drive_it(config):
    """Its interface is not Claude Code's TUI, and the loop's gate detection is.
    Reported as not drivable beats quietly mis-driven."""
    assert session.drivable(_agent(config).spec) is False


def test_and_the_agents_table_says_attended_rather_than_no(config, monkeypatch):
    """A bare "no" would read as broken. It runs; the loop cannot read it."""
    from typer.testing import CliRunner
    from ai4science.cli import app
    # A wide terminal, because the assertion is about what the table SAYS and
    # this id is long enough that rich wraps it mid-word in a narrow one.
    monkeypatch.setenv("COLUMNS", "200")
    out = CliRunner().invoke(app, ["sarsi", "agents"]).output
    assert "computational-imaging" in out
    line = [l for l in out.splitlines() if "computational-imaging" in l][0]
    assert "attended" in line, "a bare interface name would not say the loop cannot read it"
    assert "retired" not in line


# ── routing ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("demand", [
    "settle the CASSI mask convention",
    "run the hyperspectral reconstruction and report PSNR",
    "the coded aperture forward model disagrees between papers",
])
def test_the_fields_own_words_reach_it(config, demand):
    got = triage.suggest(config, demand)
    assert got.best is not None, demand
    assert got.best.agent_id == "computational-imaging", (demand, got.best.agent_id)


@pytest.mark.parametrize("demand", [
    "fix the failing test in the repo",
    "run the benchmark and tell me what changed",
    "analyse this data and write a script",
])
def test_but_ordinary_work_still_goes_to_the_general_worker(config, demand):
    """The failure this guards: a research field quietly capturing every request
    that mentions a benchmark, which would look like the router being clever."""
    got = triage.suggest(config, demand)
    assert got.best is not None, demand
    assert got.best.agent_id == "sarsi-worker", (demand, got.best.agent_id)


def test_it_does_not_hold_the_general_workers_vocabulary():
    entry = [a for a in reg._ROSTER if a["id"] == "computational-imaging"][0]
    worker = [a for a in reg._ROSTER if a["id"] == "sarsi-worker"][0]
    assert not (set(entry.get("about", [])) & set(worker.get("about", []))), \
        "two agents claiming one word is a tie the router has to break by luck"


# ── the workspace it gets ─────────────────────────────────────────────

def test_it_gets_its_own_workspace_and_task_list(config):
    a = _agent(config)
    assert a.workspace.exists(), "installed agents get a workspace (§11z)"
    assert a.workspace != _agent(config, "sarsi-worker").workspace


def test_and_it_starts_at_the_everyday_ceiling_like_everything_else(config):
    """A research agent is not an exception to the ceiling. Being the governor's
    buys being written, not being trusted further."""
    assert _agent(config).ceiling == reg.EVERYDAY_CEILING


def test_nor_the_general_workers_tools(config):
    """The same argument as the vocabulary, and I applied it only to `about` the
    first time. `tools` feeds routing as well: declaring `editor` here tied with
    `sarsi-worker` on "open the editor and fix the header", and a tie makes the
    router answer "I cannot tell" — strictly worse than the answer it replaced.
    """
    entry = [a for a in reg._ROSTER if a["id"] == "computational-imaging"][0]
    worker = [a for a in reg._ROSTER if a["id"] == "sarsi-worker"][0]
    assert not (set(entry.get("tools", [])) & set(worker.get("tools", [])))


def test_and_the_generic_editor_request_still_resolves(config):
    got = triage.suggest(config, "open the editor and fix the header")
    assert got.best is not None, "a tie here means the router cannot answer"
    assert got.best.agent_id == "sarsi-worker"

"""Each sarsi agent is built on an existing ai4science agent spec.

The registry already holds `manager`, `machine`, `social`, `pocket`, `research`,
`claude-code` and the domain agents. The seven workers are an orchestration
layer over those, not a second stack beside them: a sarsi agent names the spec
its sessions run, and that spec is one of the ones already installed.

Two rules:

  * **a spec that is not installed is refused, by name.** Silently falling back
    to a generalist would run the wrong agent under the right label, which is
    worse than not starting.
  * **the loop only drives what it can read.** Its screen-reading — gates,
    stranded prompts, the busy marker — is tuned to Claude Code's TUI. A spec
    that runs a different interface may be started, and is reported as not
    drivable unattended rather than quietly mis-driven.
"""
import pytest

from ai4science.harness.agents.sarsi import (admin, registry as reg,
                                             session as ses, task as tsk, worker)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path,
                  path=tmp_path / "sarsi.json")
    c.ensure_dirs()
    return c


class FakeRuntime:
    engine = "claude"

    def __init__(self):
        self.started = []

    def start(self, name, cwd, *, govern, ceiling, env=None, spec=None,
              writable=None):
        self.started.append({"name": name, "spec": spec})
        return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

    def send(self, name, text):
        return {"ok": True}

    def set_ceiling(self, name, ceiling):
        return {"ok": True}


# ── every agent names the spec it is built on ─────────────────────────

def test_each_agent_declares_a_spec(config):
    for name, agent in config.agents.items():
        assert agent.spec, f"{name} names no ai4science agent spec"


def test_the_defaults_reuse_specs_that_already_exist(config):
    """`manager` for the manager, `social` for social — the registry was
    written for these roles."""
    assert config.agents["sarsi-machine"].spec == "manager"
    assert config.agents["social"].spec == "social"
    assert config.agents["work"].spec == "claude-code"


def test_a_spec_can_be_set_per_agent(tmp_path):
    raw = reg.default_config(owner_id="1")
    for entry in raw["agents"]["list"]:
        if entry["id"] == "funding":
            entry["spec"] = "research"
    c = reg.parse(raw, root=tmp_path)
    assert c.agents["funding"].spec == "research"


def test_a_registry_written_before_specs_existed_still_binds_correctly(tmp_path):
    """A config from an older build carries no `spec` on any entry. Defaulting
    those to `claude-code` would silently unbind every agent — the table would
    say `claude-code` seven times and look like the feature was working."""
    raw = reg.default_config(owner_id="1")
    for entry in raw["agents"]["list"]:
        entry.pop("spec", None)
    c = reg.parse(raw, root=tmp_path)
    assert c.agents["sarsi-machine"].spec == "manager"
    assert c.agents["abraham"].spec == "pocket"
    assert c.agents["social"].spec == "social"


def test_an_agent_the_roster_does_not_know_still_gets_a_usable_default(tmp_path):
    raw = reg.default_config(owner_id="1")
    raw["agents"]["list"].append({"id": "extra", "role": "worker"})
    c = reg.parse(raw, root=tmp_path)
    assert c.agents["extra"].spec == "claude-code"


def test_the_agents_table_shows_which_spec_each_is_built_on(config):
    rows = {r["id"]: r for r in admin.agent_rows(config)}
    assert rows["social"]["spec"] == "social"


# ── the session runs that spec ────────────────────────────────────────

def _task(config, agent):
    d = worker.Directive(agent_id=agent.id, goal="a job")
    return tsk.create(config, agent, d)


def test_the_session_is_started_with_the_agents_spec(config):
    """CHANGED by the backend work, deliberately, and worth the paragraph.

    This asserted `claude-code` for `work`, whose roster spec is `claude-code`.
    The owner then set the default the other way: "when sarsi-worker makes a
    task, give the choice sarsi-claude or sarsi-pwm — **default is sarsi-pwm**",
    and sarsi-pwm means "ai4science, not the vendor binary". An agent whose spec
    is `claude-code` therefore takes the ai4science default unless the task
    explicitly chooses `sarsi-claude`.

    What this test still guards is the part that did not change: a spec is not
    SUBSTITUTED. `social` starts `social`, `computational-imaging` starts
    `computational-imaging` — see the tests below and
    `test_sarsi_pwm_runs_the_agents_own_spec` in test_backends.py. Only the
    `claude-code` spec is special, and only because one backend exists to avoid
    requiring the vendor CLI at all.
    """
    agent = config.agents["work"]
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started[0]["spec"] == "ai4sci"   # sarsi-pwm's canonical spec (was 'unified-LLM')

    from ai4science.harness.agents.sarsi import task as _t
    t = _task(config, agent); t.backend = "sarsi-claude"
    rt2 = FakeRuntime()
    ses.assign(config, agent, t, runtime=rt2)
    assert rt2.started[0]["spec"] == "claude-code", (
        "naming sarsi-claude must still start the vendor binary")


def test_a_different_agent_starts_a_different_spec(config):
    agent = config.agents["social"]
    rt = FakeRuntime()
    ses.assign(config, agent, _task(config, agent), runtime=rt)
    assert rt.started[0]["spec"] == "social"


# ── an uninstalled spec is refused, not substituted ───────────────────

def test_an_uninstalled_spec_is_refused_by_name(config):
    agent = config.agents["work"]
    agent.spec = "not-a-real-agent"
    rt = FakeRuntime()
    with pytest.raises(ses.SpecUnavailable, match="not-a-real-agent"):
        ses.assign(config, agent, _task(config, agent), runtime=rt,
                   installed=lambda: {"claude-code", "social"})
    assert rt.started == []


def test_the_refusal_names_what_is_installed(config):
    agent = config.agents["work"]
    agent.spec = "ghost"
    try:
        ses.assign(config, agent, _task(config, agent), runtime=FakeRuntime(),
                   installed=lambda: {"claude-code", "research"})
    except ses.SpecUnavailable as e:
        assert "claude-code" in str(e) and "research" in str(e)


def test_it_never_substitutes_a_generalist(config):
    """Running the wrong agent under the right label is worse than not
    starting."""
    agent = config.agents["funding"]
    agent.spec = "ghost"
    rt = FakeRuntime()
    with pytest.raises(ses.SpecUnavailable):
        ses.assign(config, agent, _task(config, agent), runtime=rt,
                   installed=lambda: {"unified-LLM"})
    assert rt.started == []


# ── what the loop can actually drive ──────────────────────────────────

def test_a_claude_code_spec_is_drivable(config):
    assert ses.drivable("claude-code") is True


def test_another_interface_is_reported_as_not_drivable(config):
    """The screen-reading is tuned to Claude Code's TUI. Saying so beats
    mis-driving a different one."""
    assert ses.drivable("research") is False


def test_the_agents_table_says_which_can_run_unattended(config):
    rows = {r["id"]: r for r in admin.agent_rows(config)}
    assert rows["work"]["unattended"] is True
    assert rows["social"]["unattended"] is False

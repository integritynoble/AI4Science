"""What the seven run at, and why it has now been both values.

**A2 is the everyday ceiling**, by the owner's decision on 2026-08-07: "the
default is A2; users can set into A1 or A0."

This file previously argued the other way, and the argument is kept because it
is the cost of the current default. The roster shipped at A2, was lowered to A1
because A2-as-default made A2 the ceiling of *every* ordinary released task —
so "A2 may do consequential things" meant every run could, and A2 stopped being
an elevated tier while still being described as one — and is now back at A2
because the owner wants ordinary work to finish without a gate at every
consequential step.

| | what it permits | the consequence |
|---|---|---|
| **A0** | reads; everything else asks | what planning runs at, always |
| **A1** | in-project writes, network, running and testing | a consequential command stops for the owner |
| **A2** | **the everyday ceiling** — all of A1, plus `git push`, `pip install`, `sudo` | an ordinary released task can do those on its own |
| **A3** | anything, including unclassifiable commands | cannot be set, only earned: capped to A2 until the trust ledger unlocks it |

Lower a specific agent with `admin.set_ceiling("<agent>", "A1")`.

**An existing registry is not rewritten.** A stored ceiling is indistinguishable
from a deliberate one, and rewriting it silently is the same class of move as
silently raising it.
"""
import pytest

from ai4science.harness.agents.machine.session import decide_tool_call
from ai4science.harness.agents.sarsi import admin, registry as reg

EVERYDAY = "A2"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    # The TRUST ledger lives outside SARSI_STATE_DIR, in the real
    # `~/.local/share/pwm-cp/`, and `trust.effective_ceiling` caps a requested
    # A3 to A2 unless A3 is unlocked there. So an A3 assertion in this file
    # passed only because THIS developer's machine happens to have A3
    # unlocked, and failed in a full run where an earlier test moved the state
    # dir — a result about the box, reported as a result about the renderer.
    #
    # Point it at the test's own directory and unlock explicitly: what is under
    # test is that the listing MARKS an elevated agent, not whether this
    # machine has earned one.
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path / "cp"))
    from ai4science.harness.agents.machine import trust
    trust.unlock_a3(force=True)
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


# ── the everyday ceiling ──────────────────────────────────────────────

def test_a_new_registry_runs_the_seven_at_the_everyday_ceiling(config):
    for agent in config.agents.values():
        assert agent.ceiling == EVERYDAY, agent.id


def test_it_does_the_work_a_task_was_released_to_do():
    write = {"tool_name": "Write", "tool_input": {"file_path": "/work/out.md"}}
    net = {"tool_name": "WebFetch", "tool_input": {"url": "https://x"}}
    test = {"tool_name": "Bash", "tool_input": {"command": "pytest -q"}}
    for call in (write, net, test):
        got = decide_tool_call(call, ceiling=EVERYDAY, project_dir="/work")
        assert got["decision"] == "allow", (call, got)


@pytest.mark.parametrize("command", [
    "git push origin main",
    "pip install requests",
    "sudo systemctl restart nginx",
])
def test_a_consequential_command_is_permitted_at_the_everyday_ceiling(command):
    """THE COST OF THE DEFAULT, asserted so it is stated rather than
    discovered: at A2 an ordinary released task can push, install and sudo
    without stopping for the owner.

    This test asserted `ask` while the everyday ceiling was A1. It is inverted
    here deliberately, not because the code changed under it."""
    got = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": command}},
                           ceiling=EVERYDAY, project_dir="/work")
    assert got["decision"] == "allow", command


@pytest.mark.parametrize("command", [
    "git push origin main",
    "pip install requests",
    "sudo systemctl restart nginx",
])
def test_and_lowering_an_agent_to_a1_brings_that_back(command):
    """The owner's escape hatch has to actually work, or "users can set into A1"
    is a sentence rather than a control."""
    got = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": command}},
                           ceiling="A1", project_dir="/work")
    assert got["decision"] == "ask", command


def test_a3_is_what_is_elevated_now():
    """With A2 as the everyday, A3 is the tier that means something — and it is
    the one that cannot be set, only earned."""
    from ai4science.harness.agents.machine import trust
    assert trust.effective_ceiling("A3") == ("A3" if trust.a3_unlocked() else "A2")
    got = decide_tool_call({"tool_name": "Bash",
                            "tool_input": {"command": "frobnicate --wat"}},
                           ceiling=EVERYDAY, project_dir="/work")
    assert got["decision"] == "ask", "an unclassifiable command needs A3"


def test_planning_still_drops_below_it(config):
    """A0 is not affected by any of this — it is set per session, not per
    agent, and it is what the plan step runs at."""
    got = decide_tool_call({"tool_name": "Write",
                            "tool_input": {"file_path": "/work/out.md"}},
                           ceiling="A0", project_dir="/work")
    assert got["decision"] == "ask"


# ── an existing registry keeps what it has, and says so ───────────────

def test_a_stored_ceiling_is_not_rewritten(tmp_path):
    """Silently lowering a recorded permission is the same class of move as
    silently raising one. What was written stays written."""
    raw = reg.default_config(owner_id="1")
    for entry in raw["agents"]["list"]:
        entry["ceiling"] = "A3"
    c = reg.parse(raw, root=tmp_path)
    assert c.agents["sarsi-worker"].ceiling == "A3"


def test_the_listing_marks_an_agent_above_the_everyday_ceiling(tmp_path):
    raw = reg.default_config(owner_id="1")
    raw["agents"]["list"][1]["ceiling"] = "A3"
    c = reg.parse(raw, root=tmp_path)
    c.ensure_dirs()
    rows = {r["id"]: r for r in admin.agent_rows(c)}
    assert rows[raw["agents"]["list"][1]["id"]]["elevated"] is True


def test_and_leaves_the_ordinary_ones_alone(config):
    rows = admin.agent_rows(config)
    assert all(r["elevated"] is False for r in rows), rows


def test_the_everyday_ceiling_is_named_once(config):
    """Two places that both decide what "ordinary" means will disagree."""
    assert reg.EVERYDAY_CEILING == EVERYDAY


# ── and the owner is told, in the listing they read ───────────────────

def test_the_rendered_listing_marks_an_elevated_agent(isolated):
    """An existing machine keeps its stored A2 and would otherwise learn about
    it never. Asserted on the OUTPUT, not on `agent_rows` — that is the mistake
    the retired flag made, where the record carried it and the table did not."""
    import json
    from typer.testing import CliRunner
    from ai4science.cli import app as cli
    runner = CliRunner()
    runner.invoke(cli, ["sarsi", "init", "--owner-id", "7007143162"])
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    for entry in raw["agents"]["list"]:
        if entry["id"] == "social":
            entry["ceiling"] = "A3"
    path.write_text(json.dumps(raw))

    out = runner.invoke(cli, ["sarsi", "agents"]).output
    line = [l for l in out.splitlines() if "social" in l][0]
    assert "A3" in line
    assert "!" in line or "elevated" in line.lower(), line


def test_and_says_how_to_bring_it_down(isolated):
    import json
    from typer.testing import CliRunner
    from ai4science.cli import app as cli
    runner = CliRunner()
    runner.invoke(cli, ["sarsi", "init", "--owner-id", "7007143162"])
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    raw["agents"]["list"][1]["ceiling"] = "A3"
    path.write_text(json.dumps(raw))
    out = runner.invoke(cli, ["sarsi", "agents"]).output
    assert "sarsi ceiling" in out


def test_an_ordinary_listing_says_none_of_that(isolated):
    from typer.testing import CliRunner
    from ai4science.cli import app as cli
    runner = CliRunner()
    runner.invoke(cli, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(cli, ["sarsi", "agents"]).output
    assert "sarsi ceiling" not in out

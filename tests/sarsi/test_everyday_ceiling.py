"""A1 is what the seven run at. A2 is something the owner grants.

The roster shipped every agent at **A2**, with the reasoning stated in the file:

    A2 is the auto level the seven run at: the loop answers the ordinary gates
    itself.

That reads as a considered choice and it was one — but it made A2 the ceiling of
every ordinary released task, so "A2 may do consequential things" meant *every
run* could, and A2 stopped being an elevated tier while still being described as
one. `/etc/passwd` answering `allow` was the visible end of that.

So the ladder is put back the way it reads:

| | what it is | what it costs |
|---|---|---|
| **A0** | planning. reads allowed, everything else asks | unchanged |
| **A1** | **the everyday ceiling.** In-project writes, network, running and testing — the work a task was released to do | a **consequential** command (`git push`, `pip install`, `sudo`) now stops for the owner |
| **A2** | elevated, and granted per agent with `sarsi ceiling` | it means something again |
| **A3** | still earned, never set | unchanged |

The cost is real and is the point: those commands are consequential by
definition, and a run that reaches for one is a run the owner should see.

**An existing registry is not rewritten.** A stored `A2` is indistinguishable
from one an owner chose, and silently lowering a recorded permission would be
the same class of move as silently raising it. New machines get A1; existing
ones are *told*, in the listing, which agents sit above the everyday ceiling and
how to bring them down.
"""
import pytest

from ai4science.harness.agents.machine.session import decide_tool_call
from ai4science.harness.agents.sarsi import admin, registry as reg

EVERYDAY = "A1"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
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
def test_but_a_consequential_command_stops_for_the_owner(command):
    """The cost of the change, stated rather than discovered."""
    got = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": command}},
                           ceiling=EVERYDAY, project_dir="/work")
    assert got["decision"] == "ask", command


def test_and_a2_still_means_something():
    """Elevated, and now actually above the everyday."""
    got = decide_tool_call({"tool_name": "Bash",
                            "tool_input": {"command": "git push origin main"}},
                           ceiling="A2", project_dir="/work")
    assert got["decision"] == "allow"


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
        entry["ceiling"] = "A2"
    c = reg.parse(raw, root=tmp_path)
    assert c.agents["sarsi-worker"].ceiling == "A2"


def test_the_listing_marks_an_agent_above_the_everyday_ceiling(tmp_path):
    raw = reg.default_config(owner_id="1")
    raw["agents"]["list"][1]["ceiling"] = "A2"
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
            entry["ceiling"] = "A2"
    path.write_text(json.dumps(raw))

    out = runner.invoke(cli, ["sarsi", "agents"]).output
    line = [l for l in out.splitlines() if "social" in l][0]
    assert "A2" in line
    assert "!" in line or "elevated" in line.lower(), line


def test_and_says_how_to_bring_it_down(isolated):
    import json
    from typer.testing import CliRunner
    from ai4science.cli import app as cli
    runner = CliRunner()
    runner.invoke(cli, ["sarsi", "init", "--owner-id", "7007143162"])
    path = reg.config_path(isolated)
    raw = json.loads(path.read_text())
    raw["agents"]["list"][1]["ceiling"] = "A2"
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

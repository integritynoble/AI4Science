"""What the owner said, to one agent, on either surface.

A surface is a door, not a scope: an agent has one memory whichever door the
owner came through. So both surfaces write one log, each entry stamped with
where it arrived — the agent can then tell *what* was said everywhere, and
*where* it was said when that matters.
"""
import pytest

from ai4science.harness.agents.sarsi import ownerlog, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


def test_both_surfaces_write_one_log(config):
    work = config.agents["work"]
    ownerlog.append(config, work, "use the staging host", surface="cli")
    ownerlog.append(config, work, "and not production", surface="telegram")
    assert [e["text"] for e in ownerlog.said(config, work)] == [
        "use the staging host", "and not production"]


def test_each_entry_remembers_its_surface(config):
    work = config.agents["work"]
    ownerlog.append(config, work, "a", surface="cli")
    assert ownerlog.said(config, work)[0]["surface"] == "cli"


def test_agents_do_not_share_an_owner_log(config):
    """W_name is per agent name. What you told `work` is not `abraham`'s."""
    ownerlog.append(config, config.agents["work"], "the mail one", surface="cli")
    assert ownerlog.said(config, config.agents["abraham"]) == []


def test_already_said_finds_it_regardless_of_surface(config):
    """The point of one log: never re-ask on Telegram what was answered in the
    CLI."""
    work = config.agents["work"]
    ownerlog.append(config, work, "the deadline is Friday", surface="cli")
    assert ownerlog.already_said(config, work, "the deadline is Friday") is True


def test_already_said_is_exact_not_fuzzy(config):
    """A fuzzy match would suppress a genuinely different question that merely
    read similarly — and silently not asking is worse than asking twice."""
    work = config.agents["work"]
    ownerlog.append(config, work, "the deadline is Friday", surface="cli")
    assert ownerlog.already_said(config, work, "the deadline is Monday") is False


def test_said_is_bounded_and_keeps_the_recent_end(config):
    work = config.agents["work"]
    for i in range(60):
        ownerlog.append(config, work, f"line {i}", surface="cli")
    recent = ownerlog.said(config, work, limit=10)
    assert len(recent) == 10 and recent[-1]["text"] == "line 59"

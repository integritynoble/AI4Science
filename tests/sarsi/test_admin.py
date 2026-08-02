"""`sarsi init` and `sarsi agents list --bindings` — the two operations that
close build slice 0.

The observation that closes the slice: seven agents, isolated directories on
disk, every binding accounted for.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import admin, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


def test_init_writes_the_seven_agent_roster(isolated):
    admin.init(owner_id="7007143162")
    raw = json.loads((isolated / "sarsi.json").read_text())
    assert len(raw["agents"]["list"]) == 7


def test_init_creates_isolated_directories_for_every_agent(isolated):
    admin.init(owner_id="7007143162")
    c = reg.load()
    dirs = {a.id: a.agent_dir for a in c.agents.values()}
    assert len(set(dirs.values())) == 7                  # no two agents share one
    assert all(d.is_dir() for d in dirs.values())


def test_init_refuses_to_clobber_an_existing_registry(isolated):
    admin.init(owner_id="7007143162")
    (isolated / "agents" / "work" / "workspace" / "keep.md").write_text("mine")
    with pytest.raises(admin.AlreadyInitialised):
        admin.init(owner_id="someone-else")
    assert (isolated / "agents" / "work" / "workspace" / "keep.md").read_text() == "mine"


def test_init_requires_an_owner_id(isolated):
    """Without one, the config it writes could not be loaded anyway."""
    with pytest.raises(ValueError, match="owner"):
        admin.init(owner_id="")


def test_agent_rows_lists_every_agent_with_its_bindings(isolated):
    admin.init(owner_id="7007143162")
    rows = admin.agent_rows(reg.load())
    assert len(rows) == 7
    work = next(r for r in rows if r["id"] == "work")
    assert set(work["bindings"]) == {"telegram:work", "cli:work"}
    assert work["role"] == "worker"


def test_agent_rows_marks_which_agent_may_not_execute(isolated):
    admin.init(owner_id="7007143162")
    rows = {r["id"]: r for r in admin.agent_rows(reg.load())}
    assert rows["sarsi-machine"]["drives_sessions"] is False
    assert rows["work"]["drives_sessions"] is True


def test_agent_rows_reports_a_missing_bot_token_rather_than_hiding_it(isolated):
    """An agent with no token is unreachable on Telegram; say so."""
    admin.init(owner_id="7007143162")
    rows = {r["id"]: r for r in admin.agent_rows(reg.load())}
    assert rows["work"]["telegram"] == "no token"
    admin.set_bot_token("work", "8541204756:AA-secret")
    rows = {r["id"]: r for r in admin.agent_rows(reg.load())}
    assert rows["work"]["telegram"] == "configured"


def test_agent_rows_never_prints_a_bot_token(isolated):
    admin.init(owner_id="7007143162")
    admin.set_bot_token("work", "8541204756:AA-secret")
    rows = admin.agent_rows(reg.load())
    assert "AA-secret" not in json.dumps(rows)

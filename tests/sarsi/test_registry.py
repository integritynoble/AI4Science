"""The agent registry: seven agents, isolated directories, and a router that
never guesses.

Two rules from the spec are load-bearing and are asserted as *refusals*:
a binding naming an unknown agent is a **startup error**, not a warning; and an
unmatched account resolves to **nothing**, never to a default agent — delivering
a personal message to the work agent because a binding was missing is the
failure the bindings table exists to prevent.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


def _write(cfg, tmp_path):
    p = tmp_path / "sarsi.json"
    p.write_text(json.dumps(cfg))
    return p


def _minimal():
    return {
        "agents": {"defaults": {"model": "anthropic/claude-haiku-4-5", "ceiling": "A1"},
                   "list": [{"id": "sarsi-machine", "role": "manager"},
                            {"id": "work", "role": "worker"}]},
        "channels": {"telegram": {"ownerId": "7007143162",
                                  "accounts": {"sarsi-machine": {"botToken": "t1"},
                                               "work": {"botToken": "t2"}}},
                     "cli": {"enabled": True}},
        "bindings": [
            {"agentId": "sarsi-machine", "match": {"channel": "telegram", "accountId": "sarsi-machine"}},
            {"agentId": "work", "match": {"channel": "telegram", "accountId": "work"}},
            {"agentId": "work", "match": {"channel": "cli", "accountId": "work"}},
        ],
    }


# ── the default roster ────────────────────────────────────────────────

def test_default_config_has_one_manager_and_the_rest_workers():
    cfg = reg.default_config()
    ids = [a["id"] for a in cfg["agents"]["list"]]
    # Stated explicitly, because an agent appearing here by accident is a thing
    # the owner should have to agree to.
    assert ids == ["sarsi-machine", "sarsi-worker", "work", "social",
                   "funding", "jobs", "computational-imaging", "abraham"]
    roles = {a["id"]: a.get("role") for a in cfg["agents"]["list"]}
    assert roles["sarsi-machine"] == "manager"
    assert all(roles[i] == "worker" for i in ids if i != "sarsi-machine")


def test_abraham_has_no_standing_grants_by_default():
    """Rule B: abraham's authority is the tightest. It starts with none."""
    cfg = reg.default_config()
    abraham = next(a for a in cfg["agents"]["list"] if a["id"] == "abraham")
    assert abraham["standingGrants"] is False


# ── loading and validation ────────────────────────────────────────────

def test_load_returns_every_agent(tmp_path):
    c = reg.load(_write(_minimal(), tmp_path))
    assert set(c.agents) == {"sarsi-machine", "work"}


def test_binding_naming_an_unknown_agent_refuses_to_start(tmp_path):
    cfg = _minimal()
    cfg["bindings"].append({"agentId": "ghost",
                            "match": {"channel": "telegram", "accountId": "work"}})
    with pytest.raises(reg.ConfigError, match="ghost"):
        reg.load(_write(cfg, tmp_path))


def test_binding_naming_an_unconfigured_account_refuses_to_start(tmp_path):
    """An agent silently unreachable is worse than a daemon that won't start."""
    cfg = _minimal()
    cfg["bindings"].append({"agentId": "work",
                            "match": {"channel": "telegram", "accountId": "nobody"}})
    with pytest.raises(reg.ConfigError, match="nobody"):
        reg.load(_write(cfg, tmp_path))


def test_duplicate_agent_id_refuses_to_start(tmp_path):
    cfg = _minimal()
    cfg["agents"]["list"].append({"id": "work", "role": "worker"})
    with pytest.raises(reg.ConfigError, match="work"):
        reg.load(_write(cfg, tmp_path))


def test_missing_owner_id_refuses_to_start(tmp_path):
    """The owner gate is only as good as its narrowest check; without an owner
    id every inbound message would be from a stranger."""
    cfg = _minimal()
    del cfg["channels"]["telegram"]["ownerId"]
    with pytest.raises(reg.ConfigError, match="ownerId"):
        reg.load(_write(cfg, tmp_path))


# ── routing ───────────────────────────────────────────────────────────

def test_resolve_routes_each_account_to_its_own_agent(tmp_path):
    c = reg.load(_write(_minimal(), tmp_path))
    assert c.resolve("telegram", "work") == "work"
    assert c.resolve("telegram", "sarsi-machine") == "sarsi-machine"


def test_both_surfaces_reach_the_same_agent(tmp_path):
    """A surface is a door, not a scope."""
    c = reg.load(_write(_minimal(), tmp_path))
    assert c.resolve("cli", "work") == c.resolve("telegram", "work") == "work"


def test_unmatched_account_resolves_to_nothing(tmp_path):
    c = reg.load(_write(_minimal(), tmp_path))
    assert c.resolve("telegram", "stranger") is None      # never a default agent


# ── defaults, roles, directories ──────────────────────────────────────

def test_agent_inherits_defaults(tmp_path):
    c = reg.load(_write(_minimal(), tmp_path))
    assert c.agents["work"].model == "anthropic/claude-haiku-4-5"
    assert c.agents["work"].ceiling == "A1"


def test_the_shipped_roster_runs_at_the_everyday_ceiling(tmp_path):
    """CHANGED from A2, deliberately, and this test asserted A2.

    A2 was "the auto level the seven run at", chosen so the loop answered the
    ordinary gates itself. The cost was that A2 became the ceiling of every
    released task — so "A2 may do consequential things" meant every run could,
    and A2 was an elevated tier in name only. Now the roster ships at A1 and A2
    is something the owner grants with `sarsi ceiling`.

    Still a ceiling, not a floor: planning drops to A0, and A3 stays capped
    until the trust ledger has earned it.
    """
    c = reg.parse(reg.default_config(owner_id="1"), root=tmp_path)
    assert {a.ceiling for a in c.agents.values()} == {reg.EVERYDAY_CEILING}


def test_a2_does_not_reach_past_what_the_ledger_earned(tmp_path):
    """Raising the shipped default must not become a way around the gate."""
    c = reg.parse(reg.default_config(owner_id="1"), root=tmp_path)
    for entry in reg.default_config(owner_id="1")["agents"]["list"]:
        assert entry.get("ceiling", "A2") != "A3"
    assert all(a.ceiling in ("A0", "A1", "A2") for a in c.agents.values())


def test_agent_overrides_defaults(tmp_path):
    cfg = _minimal()
    cfg["agents"]["list"][1]["ceiling"] = "A2"
    c = reg.load(_write(cfg, tmp_path))
    assert c.agents["work"].ceiling == "A2"
    assert c.agents["sarsi-machine"].ceiling == "A1"      # untouched


def test_the_manager_is_not_a_worker(tmp_path):
    """§1: the agent you talk to does not execute."""
    c = reg.load(_write(_minimal(), tmp_path))
    assert c.agents["sarsi-machine"].is_worker is False
    assert c.agents["work"].is_worker is True


def test_ensure_dirs_gives_each_agent_its_own(tmp_path):
    c = reg.load(_write(_minimal(), tmp_path))
    c.ensure_dirs()
    work, machine = c.agents["work"], c.agents["sarsi-machine"]
    assert work.workspace.is_dir() and work.host.is_dir()
    assert work.tasks.is_dir() and work.sessions.is_dir()
    assert work.workspace != machine.workspace           # no shared workspace
    assert work.agent_dir.parent == machine.agent_dir.parent


def test_ensure_dirs_creates_the_shared_user_workspace(tmp_path):
    c = reg.load(_write(_minimal(), tmp_path))
    c.ensure_dirs()
    assert c.user_workspace.is_dir()                     # W_user — every agent reads it
    assert c.vault_dir.is_dir()                          # W_secret — nobody reads it

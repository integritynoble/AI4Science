"""The log holds both roles, and only one of them is instruction.

Asked for by the console session: its chat door renders a two-sided transcript,
and on the canonical plane the agent's reply was never written down anywhere —
the gateway handed it to the transport and dropped it, so Telegram lost its
replies too.

The risk in answering it is not the new field, it is the four existing readers.
`composer`, `answering` and `workspace` hand `said()` to the agent as *what the
owner told it*, and `already_said` decides whether a question still needs
asking. If replies appeared in any of those, the agent would read its own words
back as instruction and suppress genuine questions. Most of this file is about
that, not about the reply record.
"""
from __future__ import annotations

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


def _agent(config):
    return config.agents["work"]


def test_the_reply_is_recorded(config):
    agent = _agent(config)
    ownerlog.append(config, agent, "what is the staging host?", surface="cli")
    ownerlog.reply(config, agent, "staging is tina", surface="cli")

    both = ownerlog.transcript(config, agent)
    assert [r["text"] for r in both] == ["what is the staging host?", "staging is tina"]
    assert [ownerlog.role_of(r) for r in both] == [ownerlog.OWNER, ownerlog.AGENT]


def test_said_returns_the_owner_only(config):
    """The whole reason this is safe. Four modules feed said() to the agent."""
    agent = _agent(config)
    ownerlog.append(config, agent, "never touch production", surface="cli")
    ownerlog.reply(config, agent, "understood, staging only", surface="cli")

    assert [r["text"] for r in ownerlog.said(config, agent)] == ["never touch production"]


def test_a_reply_does_not_answer_already_said(config):
    """An agent echoing the owner must not make the question look asked.

    already_said is an exact match, so an agent that quotes the owner back --
    which is ordinary acknowledgement -- would otherwise suppress the real
    question the next time it came up."""
    agent = _agent(config)
    ownerlog.reply(config, agent, "should I use the staging host?", surface="cli")

    assert ownerlog.already_said(config, agent, "should I use the staging host?") is False
    ownerlog.append(config, agent, "should I use the staging host?", surface="cli")
    assert ownerlog.already_said(config, agent, "should I use the staging host?") is True


def test_records_without_a_role_read_as_the_owners(config):
    """Every record written before the field existed was an owner turn."""
    agent = _agent(config)
    ownerlog.append(config, agent, "from before the field", surface="cli")
    path = agent.workspace / ownerlog.LOG_NAME
    path.write_text(path.read_text().replace(', "role": "owner"', ""))

    assert '"role"' not in path.read_text()          # genuinely an old-shaped record
    assert [r["text"] for r in ownerlog.said(config, agent)] == ["from before the field"]
    assert ownerlog.role_of({"text": "x"}) == ownerlog.OWNER
    assert ownerlog.already_said(config, agent, "from before the field") is True


def test_the_limit_counts_owner_turns_not_lines(config):
    """A window of N owner turns must not shrink because the agent answered.

    said(limit=5) is what composer asks for. If the trim ran over raw lines,
    an answered conversation would give it two or three owner turns instead of
    five, and the agent would quietly lose context the moment replies started
    being recorded."""
    agent = _agent(config)
    for i in range(8):
        ownerlog.append(config, agent, f"owner {i}", surface="cli")
        ownerlog.reply(config, agent, f"reply {i}", surface="cli")

    window = ownerlog.said(config, agent, limit=5)
    assert [r["text"] for r in window] == [f"owner {i}" for i in range(3, 8)]


def test_transcript_is_per_agent(config):
    """Same isolation as said(): what you told work is not abraham's to read."""
    ownerlog.reply(config, config.agents["work"], "work answered", surface="cli")
    assert ownerlog.transcript(config, config.agents["abraham"]) == []

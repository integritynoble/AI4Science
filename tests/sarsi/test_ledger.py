"""The append-only ledgers: what was asked, what was decided, what was refused.

A ledger is the only durable answer to *"what did this agent actually do?"*, so
it may never be rewritten, and it may never hold a secret — the vault ledger
records the **question** and the **decision**, never the value.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import ledger, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


def test_append_then_read_round_trips(config):
    ledger.append(config, "inbound", {"agent": "work", "kind": "message"})
    assert [r["agent"] for r in ledger.read(config, "inbound")] == ["work"]


def test_appends_accumulate_and_never_overwrite(config):
    for i in range(3):
        ledger.append(config, "inbound", {"n": i})
    assert [r["n"] for r in ledger.read(config, "inbound")] == [0, 1, 2]


def test_every_record_is_stamped(config):
    ledger.append(config, "inbound", {"n": 1}, now=lambda: 1754150400.0)
    assert ledger.read(config, "inbound")[0]["at"].startswith("2025-")


def test_reading_an_empty_ledger_is_empty_not_an_error(config):
    assert ledger.read(config, "outward") == []


def test_count_matches_on_fields(config):
    ledger.append(config, "inbound", {"reason": "not-owner"})
    ledger.append(config, "inbound", {"reason": "not-owner"})
    ledger.append(config, "inbound", {"reason": "no-binding"})
    assert ledger.count(config, "inbound", reason="not-owner") == 2
    assert ledger.count(config, "inbound") == 3


def test_a_secret_bearing_field_is_refused(config):
    """The rule is enforced where it is cheap: at the write."""
    with pytest.raises(ledger.SecretInLedger, match="botToken"):
        ledger.append(config, "inbound", {"agent": "work", "botToken": "8541:AA"})


def test_naming_a_secret_is_allowed_carrying_its_value_is_not(config):
    """`VLT` must record WHICH secret was asked for, so the owner can grant it."""
    ledger.append(config, "vault", {"secret": "mail.read", "decision": "DENY"})
    assert ledger.read(config, "vault")[0]["secret"] == "mail.read"


def test_a_corrupt_line_does_not_lose_the_rest(config):
    ledger.append(config, "inbound", {"n": 1})
    path = config.ledger_dir / "inbound.jsonl"
    with path.open("a") as fh:
        fh.write("{not json\n")
    ledger.append(config, "inbound", {"n": 2})
    assert [r["n"] for r in ledger.read(config, "inbound")] == [1, 2]


def test_the_ledger_file_is_owner_only(config):
    ledger.append(config, "inbound", {"n": 1})
    mode = (config.ledger_dir / "inbound.jsonl").stat().st_mode & 0o777
    assert mode == 0o600

import pytest

from ai4science.harness.agents.machine import trust


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_TRUST_OWNER", "tester")
    monkeypatch.setenv("PWM_A3_THRESHOLD", "3")
    return tmp_path


def test_record_increments_counters():
    trust.record("approve"); trust.record("approve"); trust.record("deny")
    s = trust.status()
    assert s["approvals"] == 2 and s["denials"] == 1 and s["forbidden_trips"] == 0
    assert s["updated"] is not None


def test_eligible_after_threshold_with_no_trips():
    for _ in range(3):
        trust.record("approve")
    assert trust.is_a3_eligible() is True


def test_forbidden_trip_voids_eligibility():
    for _ in range(5):
        trust.record("approve")
    trust.record("forbidden")
    assert trust.is_a3_eligible() is False        # a single catastrophe attempt voids it


def test_unlock_refused_until_eligible():
    r = trust.unlock_a3()
    assert r["ok"] is False and "locked" in r["reason"].lower()
    assert trust.a3_unlocked() is False
    for _ in range(3):
        trust.record("approve")
    r = trust.unlock_a3()
    assert r["ok"] is True and trust.a3_unlocked() is True


def test_effective_ceiling_downgrades_a3_until_unlocked():
    assert trust.effective_ceiling("A3") == "A2"      # locked → capped
    assert trust.effective_ceiling("A1") == "A1"      # others pass through
    for _ in range(3):
        trust.record("approve")
    trust.unlock_a3()
    assert trust.effective_ceiling("A3") == "A3"      # unlocked → honored


def test_status_empty_defaults():
    s = trust.status()
    assert s == {"approvals": 0, "denials": 0, "forbidden_trips": 0,
                 "a3_unlocked": False, "updated": None}

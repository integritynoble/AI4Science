from ai4science.harness import onboard_tools
from ai4science.harness.onboard_tools import onboard_tools as build


def _tools():
    return {t.name: t for t in build()}


def test_balance_no_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_balance"].func(tmp_path)
    assert "[onboard error]" in out and "PWM_ONBOARD_TOKEN" in out


def test_balance_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_get_json",
                        lambda path: {"success": True, "balance": 0.3, "daily_remaining": 1.7})
    out = _tools()["onboard_balance"].func(tmp_path)
    assert "0.3" in out and "success" not in out


def test_status_lists_transactions(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_get_json",
                        lambda path: {"success": True, "transactions": [
                            {"kind": "award", "amount": 0.1, "status": "accepted",
                             "created_at": "2026-06-06"}]})
    out = _tools()["onboard_status"].func(tmp_path)
    assert "award" in out and "0.1" in out and "accepted" in out


def test_status_no_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_status"].func(tmp_path)
    assert "[onboard error]" in out

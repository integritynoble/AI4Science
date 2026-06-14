"""`ai4science compute join` — open provider onboarding (earn PWM)."""
import pytest
from typer.testing import CliRunner

from ai4science.commands.compute import app
from ai4science.compute.registry import load_registry

WALLET = "0xAbc1230000000000000000000000000000004444"


@pytest.fixture(autouse=True)
def _isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "providers.json"))
    yield


def test_join_registers_open_provider_with_wallet_and_concurrency(tmp_path):
    res = CliRunner().invoke(app, [
        "join", "--wallet", WALLET, "--kind", "cpu",
        "--max-concurrent", "2", "--price-pwm-per-hour", "0.04",
        "--endpoint", str(tmp_path / "inbox"),
    ])
    assert res.exit_code == 0, res.output
    provs = {p.provider_id: p for p in load_registry()}
    assert len(provs) == 1
    p = next(iter(provs.values()))
    assert p.wallet_address == WALLET
    assert p.kind == "cpu"
    assert p.trust_tier == "open"          # community tier, not founder
    assert p.pwm_per_hour() == 0.04        # priced natively in PWM/hr
    assert p.max_concurrent == 2           # honors the explicit --max-concurrent flag
    # tells the user how to earn + how to start serving
    assert "earn PWM" in res.output or "How you earn PWM" in res.output
    assert "compute serve" in res.output


def test_join_defaults_price_by_kind(tmp_path):
    CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "gpu",
                             "--endpoint", str(tmp_path / "g")])
    p = load_registry()[0]
    assert p.pwm_per_hour() == 0.30        # gpu default (PWM/hr)


def test_join_rejects_bad_wallet(tmp_path):
    res = CliRunner().invoke(app, ["join", "--wallet", "nope",
                                   "--endpoint", str(tmp_path / "x")])
    assert res.exit_code == 2
    assert load_registry() == []


def test_providers_add_accepts_max_concurrent(tmp_path):
    res = CliRunner().invoke(app, [
        "providers-add", "--id", "p1", "--wallet", WALLET,
        "--endpoint", str(tmp_path / "i"), "--kind", "gpu",
        "--max-concurrent", "4",
    ])
    assert res.exit_code == 0, res.output
    assert load_registry()[0].max_concurrent == 4

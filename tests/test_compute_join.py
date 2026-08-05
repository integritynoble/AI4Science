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
        "join", "--wallet", WALLET, "--kind", "cpu", "--system", "linux",
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


def test_join_defaults_price_by_kind(tmp_path, monkeypatch):
    from ai4science.compute import host
    monkeypatch.setattr(host, "_run", lambda cmd, **kw:
                        "NVIDIA A100-SXM4-40GB, 40960 MiB, 12.7")
    CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "gpu",
                             "--system", "linux",
                             "--endpoint", str(tmp_path / "g")])
    p = load_registry()[0]
    assert p.pwm_per_hour() == 0.30        # gpu default (PWM/hr)


def test_join_rejects_bad_wallet(tmp_path):
    res = CliRunner().invoke(app, ["join", "--wallet", "nope",
                                   "--system", "linux", "--kind", "cpu",
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


# ── the exchange node exchanges compute, so it asks what the box is ───
#
# `--kind gpu` was taken on the provider's word. That holds while the only
# providers are the owner's own two boxes and breaks the moment anyone else
# joins: a solver built against CUDA on Linux does not run on Windows, and a
# claimed GPU that is not there is discovered by the first heavy job — which for
# the agents that need this at all (computational imaging above everything) is
# an expensive place to find out.

def test_join_asks_which_system_will_serve(tmp_path):
    """Not sniffed from this process: `join` gets run from WSL, from
    containers and over SSH, and the box that serves is the one a solver has
    to match."""
    res = CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "cpu",
                                   "--endpoint", str(tmp_path / "i")])
    assert res.exit_code == 2
    assert "which system" in res.output.lower() or "--system" in res.output
    assert load_registry() == []


def test_join_records_the_declared_system(tmp_path):
    res = CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "cpu",
                                   "--system", "windows",
                                   "--endpoint", str(tmp_path / "i")])
    assert res.exit_code == 0, res.output
    assert load_registry()[0].gpu_capability["system"] == "windows"


def test_join_refuses_a_system_it_cannot_route_to(tmp_path):
    res = CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "cpu",
                                   "--system", "freebsd",
                                   "--endpoint", str(tmp_path / "i")])
    assert res.exit_code == 2
    assert "freebsd" in res.output


def test_join_detects_the_gpu_rather_than_believing_the_flag(tmp_path, monkeypatch):
    from ai4science.compute import host
    monkeypatch.setattr(host, "_run", lambda cmd, **kw:
                        "NVIDIA GeForce RTX 4090, 24564 MiB, 12.4")
    res = CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "gpu",
                                   "--system", "linux",
                                   "--endpoint", str(tmp_path / "i")])
    assert res.exit_code == 0, res.output
    cap = load_registry()[0].gpu_capability
    assert cap["detected"] is True and "4090" in cap["device"]
    assert "4090" in res.output          # the provider is shown what was found


def test_offering_a_gpu_the_machine_does_not_have_is_refused(tmp_path, monkeypatch):
    from ai4science.compute import host
    monkeypatch.setattr(host, "_run", lambda cmd, **kw: None)
    res = CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "gpu",
                                   "--system", "linux",
                                   "--endpoint", str(tmp_path / "i")])
    assert res.exit_code == 2
    assert "no GPU" in res.output
    assert load_registry() == []


def test_a_probe_that_could_not_run_still_registers(tmp_path, monkeypatch):
    """Unknown is not none. Locking out a provider whose driver was unreadable
    treats something never observed as an observed absence."""
    from ai4science.compute import host
    def explode(cmd, **kw):
        raise OSError("permission denied")
    monkeypatch.setattr(host, "_run", explode)
    res = CliRunner().invoke(app, ["join", "--wallet", WALLET, "--kind", "gpu",
                                   "--system", "linux",
                                   "--endpoint", str(tmp_path / "i")])
    assert res.exit_code == 0, res.output
    cap = load_registry()[0].gpu_capability
    assert cap["observed"] is False and cap["detected"] is False

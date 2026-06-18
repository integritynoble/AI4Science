"""`ai4science provider start` — the one-command GPU-provider plug-in."""
import os
from typer.testing import CliRunner

import ai4science.cli as climod
from ai4science import wallet as W
from ai4science.commands import provider as provider_cmd

runner = CliRunner()


def _clear_token():
    for k in ("AI4SCIENCE_PWM_TOKEN", "PWM_TOKEN", "PWM_ONBOARD_TOKEN"):
        os.environ.pop(k, None)


def test_provider_start_registered_in_cli():
    res = runner.invoke(climod.app, ["provider", "start", "--help"])
    assert res.exit_code == 0
    assert "--wallet" in res.output and "--allow-exec" in res.output


def test_provider_start_requires_login(monkeypatch):
    _clear_token()
    monkeypatch.setattr(W, "platform_token", lambda: None)
    res = runner.invoke(climod.app, ["provider", "start", "--wallet", "0x" + "a" * 40])
    assert res.exit_code == 2 and "Not logged in" in res.output


def test_provider_start_rejects_bad_wallet(monkeypatch):
    monkeypatch.setattr(W, "platform_token", lambda: "tok")
    res = runner.invoke(climod.app, ["provider", "start", "--wallet", "nothex"])
    assert res.exit_code == 2 and "0x" in res.output


def test_provider_start_registers_then_serves(monkeypatch):
    monkeypatch.setattr(W, "platform_token", lambda: "tok")
    monkeypatch.setattr(W, "platform_base", lambda: "https://x")
    posted = {}

    def _post(base, path, token, body):
        posted["path"] = path
        posted["body"] = body
        return 200, {"success": True, "provider_id": body["provider_id"]}
    monkeypatch.setattr(W, "http_post", _post)

    served = {}

    def _serve(provider, base_url, *, token="", allow_exec=False, once=False, on_event=None):
        served["provider"] = provider
        served["token"] = token
        served["allow_exec"] = allow_exec
    monkeypatch.setattr("ai4science.compute.http_provider.serve_http", _serve)

    res = runner.invoke(climod.app, ["provider", "start", "--wallet", "0x" + "c" * 40,
                                     "--id", "mybox-gpu", "--allow-exec", "--once",
                                     "--price", "0.5"])
    assert res.exit_code == 0, res.output
    # registered to the right endpoint with wallet + price
    assert posted["path"] == "/api/v1/compute/providers"
    assert posted["body"]["wallet_address"] == "0x" + "c" * 40
    assert posted["body"]["provider_id"] == "mybox-gpu"
    assert posted["body"]["price_pwm_per_hour"] == 0.5
    # then served with the owner's token (per-provider auth) + allow_exec
    assert served["token"] == "tok" and served["allow_exec"] is True
    assert served["provider"]["provider_id"] == "mybox-gpu"

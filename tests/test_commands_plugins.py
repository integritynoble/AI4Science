"""ai4science plugins — pull/list/installed against a mocked gallery."""
import json

import pytest
from typer.testing import CliRunner

from ai4science.commands import plugins as pcmd
from ai4science.harness import transport

runner = CliRunner()

GALLERY = {
    "plugins": [
        {"name": "spectral-pro", "kind": "agent", "title": "Spectral Pro",
         "target_agent": "spectral-pro", "price_pwm": 3},
        {"name": "denoise-suite", "kind": "tool", "title": "Denoise",
         "target_agent": "research", "price_pwm": 0},
    ]
}
MANIFESTS = {
    "spectral-pro": {"kind": "agent", "name": "spectral-pro", "title": "Spectral Pro",
                     "description": "d", "tier": "science", "wallet": "0xfeed", "price_pwm": 3},
    "denoise-suite": {"kind": "tool", "name": "denoise-suite", "title": "Denoise",
                      "description": "d", "mcp_servers": [{"name": "denoise"}],
                      "attach_to": ["research"], "wallet": "0xtool"},
    "broken-one": {"kind": "agent", "name": "broken-one"},  # missing title/description
}


@pytest.fixture
def mock_gallery(monkeypatch, tmp_path):
    def fake_get_json(url, timeout=60):
        if url.endswith("/api/v1/plugins"):
            return GALLERY
        if url.endswith("/manifest"):
            name = url.split("/api/v1/plugins/")[1].rsplit("/manifest", 1)[0]
            if name not in MANIFESTS:
                raise RuntimeError("HTTP 404")
            return MANIFESTS[name]
        raise RuntimeError(f"unexpected url {url}")
    monkeypatch.setattr(transport, "get_json", fake_get_json)
    monkeypatch.setenv("AI4SCIENCE_PLUGINS_DIR", str(tmp_path / "plugins"))
    return tmp_path / "plugins"


def test_default_base_is_physicsworldmodel():
    assert pcmd.DEFAULT_BASE == "https://physicsworldmodel.org"
    assert pcmd._base(None) == "https://physicsworldmodel.org"


def test_list_shows_gallery(mock_gallery):
    res = runner.invoke(pcmd.app, ["list"])
    assert res.exit_code == 0
    assert "spectral-pro" in res.stdout and "denoise-suite" in res.stdout


def test_pull_named_writes_valid_manifest(mock_gallery):
    res = runner.invoke(pcmd.app, ["pull", "spectral-pro"])
    assert res.exit_code == 0
    dest = mock_gallery / "spectral-pro.json"
    assert dest.exists()
    assert json.loads(dest.read_text())["name"] == "spectral-pro"
    assert "installed" in res.stdout


def test_pull_all_installs_whole_gallery(mock_gallery):
    res = runner.invoke(pcmd.app, ["pull", "--all"])
    assert res.exit_code == 0
    assert (mock_gallery / "spectral-pro.json").exists()
    assert (mock_gallery / "denoise-suite.json").exists()


def test_pull_requires_a_name(mock_gallery):
    res = runner.invoke(pcmd.app, ["pull"])
    assert res.exit_code == 2
    assert "Name a plug-in" in res.stdout


def test_pull_unknown_name_errors_but_continues(mock_gallery):
    res = runner.invoke(pcmd.app, ["pull", "does-not-exist", "spectral-pro"])
    assert res.exit_code == 0
    assert "404" in res.stdout
    assert (mock_gallery / "spectral-pro.json").exists()  # the good one still installs


def test_pull_validates_before_writing(mock_gallery):
    res = runner.invoke(pcmd.app, ["pull", "broken-one"])
    assert res.exit_code == 0
    assert "invalid" in res.stdout
    assert not (mock_gallery / "broken-one.json").exists()  # garbage never written


def test_pull_skips_existing_without_force(mock_gallery):
    runner.invoke(pcmd.app, ["pull", "spectral-pro"])
    res = runner.invoke(pcmd.app, ["pull", "spectral-pro"])
    assert "skip" in res.stdout and "already installed" in res.stdout


def test_pull_force_overwrites(mock_gallery):
    runner.invoke(pcmd.app, ["pull", "spectral-pro"])
    res = runner.invoke(pcmd.app, ["pull", "spectral-pro", "--force"])
    assert "installed" in res.stdout


def test_installed_lists_local(mock_gallery):
    runner.invoke(pcmd.app, ["pull", "--all"])
    res = runner.invoke(pcmd.app, ["installed"])
    assert res.exit_code == 0
    assert "spectral-pro" in res.stdout and "denoise-suite" in res.stdout


def test_pull_into_explicit_dir(mock_gallery, tmp_path):
    target = tmp_path / "custom"
    res = runner.invoke(pcmd.app, ["pull", "spectral-pro", "--dir", str(target)])
    assert res.exit_code == 0 and (target / "spectral-pro.json").exists()

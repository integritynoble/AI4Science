"""Plug-and-play agents/tools from manifests + wallet charging."""
import json

import pytest

from ai4science.harness.agents import registry, capabilities, billing
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for, dispatchable_targets
from ai4science.harness.agents import plugins


# ── fakes ──────────────────────────────────────────────────────────────────

class _FakeMCPClient:
    def __init__(self, server, tools):
        self.server = server
        self._tools = tools

    def list_tools(self):
        return self._tools

    def call_tool(self, name, args):
        return f"called {name}"


def _factory_for(toolnames):
    def factory(server_dict):
        return _FakeMCPClient(server_dict.get("name", "srv"),
                              [{"name": n, "description": n} for n in toolnames])
    return factory


def _ctx(tmp_path, factory=None):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None, mcp_client_factory=factory)


def _write(d, name, obj):
    (d / name).write_text(json.dumps(obj), encoding="utf-8")


@pytest.fixture
def plugdir(tmp_path, monkeypatch):
    d = tmp_path / "plugins"
    d.mkdir()
    monkeypatch.setenv("AI4SCIENCE_PLUGINS_DIR", str(d))
    yield d
    registry.reload()  # restore built-ins-only registry for other tests


# ── manifest parsing ────────────────────────────────────────────────────────

def test_parse_agent_manifest_defaults_and_wallet():
    spec = plugins.parse_manifest({
        "kind": "agent", "name": "spectral-pro", "title": "Spectral Pro",
        "description": "d", "capabilities": ["ci-algorithms"],
        "wallet": "0xabc", "price_pwm": 5})
    assert spec.tier == "science" and spec.category == "specific"
    assert spec.wallet == "0xabc" and spec.price_pwm == 5.0 and spec.source == "plugin"


def test_parse_requires_fields():
    with pytest.raises(plugins.ManifestError):
        plugins.parse_manifest({"kind": "agent", "name": "x"})  # no title/description


def test_parse_rejects_bad_kind():
    with pytest.raises(plugins.ManifestError):
        plugins.parse_manifest({"kind": "weapon", "name": "x", "title": "t", "description": "d"})


# ── agent plug-in into the registry (moat preserved) ────────────────────────

def test_agent_plugin_registered_and_dispatchable(plugdir):
    _write(plugdir, "spectral.json", {
        "kind": "agent", "name": "spectral-pro", "title": "Spectral Pro",
        "description": "spectral recon expert", "capabilities": ["ci-algorithms"],
        "wallet": "0xfeed", "price_pwm": 3})
    registry.reload()
    spec = registry.get("spectral-pro")
    assert spec is not None and spec.source == "plugin" and spec.wallet == "0xfeed"
    # science main can dispatch to it; an open base agent cannot (moat).
    assert "spectral-pro" in dispatchable_targets(registry.get("research"))
    assert "spectral-pro" not in dispatchable_targets(registry.get("claude-code"))


def test_agent_plugin_name_collision_skipped(plugdir):
    _write(plugdir, "dupe.json", {
        "kind": "agent", "name": "research", "title": "x", "description": "d"})
    registry.reload()
    assert registry.get("research").source == "builtin"
    assert any("collides" in e for e in registry.PLUGIN_ERRORS)


def test_bad_manifest_collected_not_fatal(plugdir):
    (plugdir / "broken.json").write_text("{not json", encoding="utf-8")
    _write(plugdir, "ok.json", {"kind": "agent", "name": "ok-agent",
                                "title": "ok", "description": "d"})
    registry.reload()
    assert registry.get("ok-agent") is not None
    assert any("broken.json" in e for e in registry.PLUGIN_ERRORS)


def test_agent_plugin_unknown_capability_skipped(plugdir):
    _write(plugdir, "bad.json", {"kind": "agent", "name": "bad-cap", "title": "t",
                                 "description": "d", "capabilities": ["does-not-exist"]})
    registry.reload()
    assert registry.get("bad-cap") is None
    assert any("does-not-exist" in e for e in registry.PLUGIN_ERRORS)


# ── tool plug-in: dynamic bundle + attach_to ────────────────────────────────

def test_tool_plugin_bundle_and_attach_to(plugdir, tmp_path):
    _write(plugdir, "denoise.json", {
        "kind": "tool", "name": "denoise-suite",
        "mcp_servers": [{"name": "denoise", "command": "python"}],
        "attach_to": ["research"], "wallet": "0xtool", "price_pwm": 1})
    registry.reload()
    # the bundle exists and is referenced by research's capabilities (attach_to)
    assert "denoise-suite" in capabilities.CAPABILITY_BUNDLES
    assert "denoise-suite" in registry.get("research").capabilities
    # building research's registry resolves the bundle's MCP tools (fake factory)
    reg = build_registry_for(registry.get("research"), is_subagent=False,
                             ctx=_ctx(tmp_path, _factory_for(["denoise_run"])))
    assert "mcp__denoise__denoise_run" in reg.names()


def test_tool_plugin_no_factory_is_graceful(plugdir, tmp_path):
    _write(plugdir, "denoise.json", {
        "kind": "tool", "name": "denoise-suite",
        "mcp_servers": [{"name": "denoise"}], "attach_to": ["research"]})
    registry.reload()
    reg = build_registry_for(registry.get("research"), is_subagent=False,
                             ctx=_ctx(tmp_path, factory=None))
    assert not any(n.startswith("mcp__denoise__") for n in reg.names())  # no crash, no tools


# ── agent plug-in's own mcp_servers attach at build ─────────────────────────

def test_agent_plugin_mcp_servers_attached(plugdir, tmp_path):
    _write(plugdir, "spectral.json", {
        "kind": "agent", "name": "spectral-pro", "title": "t", "description": "d",
        "mcp_servers": [{"name": "spec"}]})
    registry.reload()
    reg = build_registry_for(registry.get("spectral-pro"), is_subagent=False,
                             ctx=_ctx(tmp_path, _factory_for(["unmix"])))
    assert "mcp__spec__unmix" in reg.names()


# ── wallet charging (reuses the gate) ───────────────────────────────────────

class _FakeGate:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.charges = []
        self.usages = []

    def charge(self, amount, provider_wallet, purpose, idempotency_key):
        self.charges.append((amount, provider_wallet, idempotency_key))
        return True, ""

    def post_usage(self, *, contribution_id, agent_name, turn_id, weight_units=1.0):
        self.usages.append((contribution_id, agent_name, turn_id))
        return True

    def _post(self, path, body):
        self.usages.append((path, body))
        return 200, {}


def _spec_with_wallet():
    return plugins.parse_manifest({
        "kind": "agent", "name": "spectral-pro", "title": "t", "description": "d",
        "wallet": "0xcafe", "price_pwm": 4})


def test_charge_plugin_use_charges_and_logs():
    g = _FakeGate(enabled=True)
    notes = billing.charge_plugin_use(_spec_with_wallet(), turn_id="t1",
                                      agent_name="computational-imaging", gate=g)
    assert g.charges == [(4.0, "0xcafe", "pluginuse:spectral-pro:t1")]
    assert g.usages == [("spectral-pro", "computational-imaging", "t1")]
    assert any("charged" in n for n in notes)


def test_charge_disabled_gate_is_noop():
    g = _FakeGate(enabled=False)
    assert billing.charge_plugin_use(_spec_with_wallet(), turn_id="t1", gate=g) == []
    assert g.charges == [] and g.usages == []


def test_charge_no_wallet_is_noop():
    spec = plugins.parse_manifest({"kind": "agent", "name": "free", "title": "t",
                                   "description": "d"})
    g = _FakeGate(enabled=True)
    assert billing.charge_plugin_use(spec, turn_id="t1", gate=g) == []


def test_register_plugin_contribution_posts():
    g = _FakeGate(enabled=True)
    assert billing.register_plugin_contribution(_spec_with_wallet(),
                                                agent_name="computational-imaging", gate=g)
    path, body = g.usages[0]
    assert path == "/api/v1/agent-pool/contributions"
    assert body["author_wallet"] == "0xcafe" and body["contribution_id"] == "spectral-pro"

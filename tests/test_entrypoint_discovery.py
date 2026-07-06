import types
from ai4science.harness.agents import registry, capabilities

class _FakeEP:
    def __init__(self, name, group, obj):
        self.name, self.group, self._obj = name, group, obj
    def load(self):
        return self._obj

def _install_fake_entrypoints(monkeypatch, specs=(), bundles=()):
    eps = [ _FakeEP(s.name, "pwm_agent.specs", s) for s in specs ]
    eps += [ _FakeEP(n, "pwm_agent.bundles", fn) for n, fn in bundles ]
    def fake_entry_points(*, group=None):
        return [e for e in eps if e.group == group]
    monkeypatch.setattr(registry, "_iter_entry_points", fake_entry_points)

def test_entrypoint_spec_discovered(monkeypatch):
    from ai4science.harness.agents.spec import AgentSpec
    demo = AgentSpec(name="demo-ep", tier="open", category="specific",
                     title="Demo", description="demo agent", capabilities=())
    _install_fake_entrypoints(monkeypatch, specs=[demo])
    registry.reload()
    assert registry.get("demo-ep") is demo

def test_entrypoint_bundle_registered(monkeypatch):
    def register():
        capabilities.register_agent_bundle(
            "demo-bundle", lambda ctx: [])
    _install_fake_entrypoints(monkeypatch, bundles=[("demo-bundle", register)])
    registry.reload()
    assert "demo-bundle" in capabilities.CAPABILITY_BUNDLES

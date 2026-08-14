"""The session mode `unified-LLM` was renamed to `ai4sci`. The old name (and the
older `common` alias) must keep working, and passing the old name explicitly must
warn LOUDLY BUT ONCE — never for internal resolution, never twice per process.

The canonical AgentSpec name comes from the INSTALLED pwm-agent-unified package,
which is not in this repo and may ship under EITHER name, so the compat alias must
work in both directions. These tests inject a fake entry-point spec (via the same
`_iter_entry_points` indirection the discovery tests use) to prove that.
"""
import pytest

from ai4science.harness.agents import registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness import tui
from ai4science.commands import chat


@pytest.fixture(autouse=True)
def _restore_default_registry():
    yield
    registry.reload()


class _FakeEP:
    def __init__(self, name, group, obj):
        self.name, self.group, self._obj = name, group, obj

    def load(self):
        return self._obj


def _install_fake_spec(monkeypatch, spec):
    ep = _FakeEP(spec.name, "pwm_agent.specs", spec)

    def fake_entry_points(*, group=None):
        return [ep] if group == "pwm_agent.specs" else []

    monkeypatch.setattr(registry, "_iter_entry_points", fake_entry_points)


def _unified_spec(name):
    return AgentSpec(name=name, tier="open", category="core",
                     title="Unified", description="unified assistant",
                     aliases=("common",))


# ── (a) both names resolve to the SAME spec, whichever the package declares ──

def test_alias_when_package_declares_unified_LLM(monkeypatch):
    spec = _unified_spec("unified-LLM")
    _install_fake_spec(monkeypatch, spec)
    registry.reload()
    assert registry.get("unified-LLM") is spec
    assert registry.get("ai4sci") is spec          # seeded compat alias
    assert registry.get("common") is spec          # package-declared alias still works


def test_alias_when_package_declares_ai4sci(monkeypatch):
    spec = _unified_spec("ai4sci")
    _install_fake_spec(monkeypatch, spec)
    registry.reload()
    assert registry.get("ai4sci") is spec
    assert registry.get("unified-LLM") is spec     # legacy name resolves forward
    assert registry.get("common") is spec


def test_seed_alias_does_not_override_a_real_spec(monkeypatch):
    # If the package somehow shipped BOTH names as real specs, the seed must not
    # clobber either — the compat alias only fills in a MISSING name.
    a = _unified_spec("ai4sci")
    u = AgentSpec(name="unified-LLM", tier="open", category="core",
                  title="Legacy", description="legacy")
    ep_a = _FakeEP("ai4sci", "pwm_agent.specs", a)
    ep_u = _FakeEP("unified-LLM", "pwm_agent.specs", u)
    monkeypatch.setattr(
        registry, "_iter_entry_points",
        lambda *, group=None: [ep_a, ep_u] if group == "pwm_agent.specs" else [])
    registry.reload()
    assert registry.get("ai4sci") is a
    assert registry.get("unified-LLM") is u


# ── (b) AI4SCIENCE_MODE=unified-LLM still selects the mode ──

def test_env_old_name_selects_the_mode(monkeypatch):
    spec = _unified_spec("ai4sci")
    _install_fake_spec(monkeypatch, spec)
    registry.reload()
    # This is exactly the chain chat.chat() runs for AI4SCIENCE_MODE=unified-LLM:
    raw = "unified-LLM"
    mode = tui.resolve_mode(raw.lower())            # display/legacy name → canonical id
    resolved, note = chat._resolve_spec(mode, registry)
    assert resolved is spec
    assert note is None


# ── (c) deprecation is loud but once, and never for internal resolution ──

class _Recorder:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))


def _fresh_recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(chat, "console", rec)
    chat._warned_deprecated_modes.clear()
    return rec


def test_deprecation_fires_once(monkeypatch):
    rec = _fresh_recorder(monkeypatch)
    chat._warn_deprecated_mode("unified-LLM")
    chat._warn_deprecated_mode("unified-LLM")
    chat._warn_deprecated_mode("UNIFIED-llm")       # case-insensitive; same key
    warns = [l for l in rec.lines if "renamed" in l]
    assert len(warns) == 1
    assert "ai4sci" in warns[0]


def test_no_deprecation_for_new_name_or_default(monkeypatch):
    rec = _fresh_recorder(monkeypatch)
    chat._warn_deprecated_mode("ai4sci")            # the new name
    chat._warn_deprecated_mode(None)                # default (nothing passed)
    chat._warn_deprecated_mode("research")          # unrelated mode
    assert [l for l in rec.lines if "renamed" in l] == []


def test_internal_resolution_never_warns(monkeypatch):
    # registry.get() resolving the legacy alias must not touch the deprecation
    # path at all — only an EXPLICIT user-supplied name warns, at the CLI edge.
    rec = _fresh_recorder(monkeypatch)
    spec = _unified_spec("ai4sci")
    _install_fake_spec(monkeypatch, spec)
    registry.reload()
    assert registry.get("unified-LLM") is spec
    assert [l for l in rec.lines if "renamed" in l] == []

from dataclasses import replace
import pytest
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness import repl


def _spec(**changes):
    base = AgentSpec(name="x", tier="science", category="specific",
                     title="X", description="x")
    return replace(base, **changes)


def test_strict_spec_selects_its_exact_route():
    spec = _spec(default_backend="pwm_qwen", default_model="qwen3.8:27b",
                 strict_route=True)
    assert repl.effective_route(spec, None, None) == (
        "pwm_qwen", "qwen3.8:27b", False)


def test_strict_spec_rejects_partial_or_conflicting_override():
    spec = _spec(default_backend="pwm_qwen", default_model="qwen3.8:27b",
                 strict_route=True)
    with pytest.raises(ValueError, match="requires pwm_qwen/qwen3.8:27b"):
        repl.effective_route(spec, "anthropic", "claude-opus-5")


def test_non_strict_spec_keeps_existing_selection_behavior():
    spec = _spec()
    backend, model, allow_fallback = repl.effective_route(spec, None, None)
    assert backend
    assert model
    assert allow_fallback is True


def test_strict_spec_rejects_backend_only_override():
    spec = _spec(default_backend="pwm_qwen", default_model="qwen3.8:27b",
                 strict_route=True)
    with pytest.raises(ValueError, match="requires pwm_qwen/qwen3.8:27b"):
        repl.effective_route(spec, "pwm_qwen", None)


def test_strict_spec_rejects_model_only_override():
    spec = _spec(default_backend="pwm_qwen", default_model="qwen3.8:27b",
                 strict_route=True)
    with pytest.raises(ValueError, match="requires pwm_qwen/qwen3.8:27b"):
        repl.effective_route(spec, None, "qwen3.8:27b")


def test_delegated_computational_imaging_uses_its_strict_route(
        tmp_path, monkeypatch):
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.agents.specs.imaging import AGENT as imaging_agent
    from ai4science.harness.events import Done, ResponseMeta, TextDelta
    from ai4science.harness.route_attestation import AttestedAdapter

    parent = _spec(name="parent", category="core")
    imaging = replace(imaging_agent, name="computational-imaging")
    monkeypatch.setattr(agent_registry, "AGENT_REGISTRY", {
        parent.name: parent, imaging.name: imaging,
    })

    adapter_backends = []

    def _adapter_for(backend):
        adapter_backends.append(backend)
        # The delegated child now speaks through the attestation guard, so the
        # stub has to PROVE the route the same way a real provider would.
        return StubAdapter([[ResponseMeta("pwm_qwen", "qwen3.8:27b",
                                          "qwen3.8:27b", "fp_ollama", "r1"),
                             TextDelta("child done"), Done("end")]])

    meter_routes = []

    def _make_meter(*, backend, model, session=None):
        meter_routes.append((backend, model))
        return lambda usage: None

    built_sessions = []
    real_session = repl.AgentSession

    def _capture_session(**kwargs):
        session = real_session(**kwargs)
        built_sessions.append((kwargs, session))
        return session

    child_context_routes = []
    real_build_registry = repl.build_registry_for

    def _capture_registry(spec, *, is_subagent, ctx):
        if is_subagent:
            child_context_routes.append((spec.name, ctx.brand_provider()))
        return real_build_registry(spec, is_subagent=is_subagent, ctx=ctx)

    monkeypatch.setattr(repl, "adapter_for", _adapter_for)
    monkeypatch.setattr(repl, "make_meter", _make_meter)
    monkeypatch.setattr(repl, "AgentSession", _capture_session)
    monkeypatch.setattr(repl, "build_registry_for", _capture_registry)
    inputs = iter(["/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl.run_common_repl(tmp_path, read_only=True,
                         backend="anthropic", model="claude-opus-5",
                         mode_label=parent.name)

    parent_session = built_sessions[0][1]
    adapter_start = len(adapter_backends)
    meter_start = len(meter_routes)
    result = parent_session.registry.get("task").func(
        tmp_path, subagent_type=imaging.name, prompt="reconstruct the CASSI cube")

    child_args = built_sessions[1][0]
    child_adapter = child_args["adapter"]
    assert result == "child done"
    # The other strict boundary: the DELEGATED child's own adapter. A child
    # handed the bare adapter would answer exactly the same way.
    assert isinstance(child_adapter, AttestedAdapter)
    assert (child_adapter.backend, child_adapter.model,
            child_adapter.strict) == ("pwm_qwen", "qwen3.8:27b", True)
    assert (child_args["backend"], child_args["model"]) == (
        "pwm_qwen", "qwen3.8:27b")
    assert adapter_backends[adapter_start:] == ["pwm_qwen"]
    assert meter_routes[meter_start:] == [("pwm_qwen", "qwen3.8:27b")]
    assert child_context_routes == [
        ("computational-imaging", ("pwm_qwen", "qwen3.8:27b"))]


def test_a_strict_session_speaks_only_through_the_attestation_guard(
        tmp_path, monkeypatch):
    """Amendment 61 names research PLANNING as one of its two boundaries, and
    the parent session's adapter IS that boundary. Nothing else in this suite
    looks at it: every hold test drives a stub that raises `StrictRouteError`
    by itself, so it would still hold if the session had been handed the bare
    `adapter_for(...)` and no guard at all. This is the instrument for the
    boundary a refactor can silently unwrap."""
    from ai4science.harness.adapters import factory
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.agents.specs.imaging import AGENT as imaging_agent
    from ai4science.harness.route_attestation import AttestedAdapter

    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    imaging = replace(imaging_agent, name="computational-imaging")
    monkeypatch.setattr(agent_registry, "AGENT_REGISTRY", {imaging.name: imaging})
    monkeypatch.setattr(factory, "harness_available", lambda backend: True)

    class Bare:
        """The unguarded adapter. It must not be what the session speaks to."""
        backend = "pwm_qwen"

        def stream(self, *_args, **_kwargs):        # pragma: no cover
            raise AssertionError("no turn runs in this test")
            yield

    bare = Bare()
    monkeypatch.setattr(repl, "adapter_for", lambda _backend: bare)
    monkeypatch.setattr(repl, "make_meter",
                        lambda **_kwargs: (lambda usage: None))

    built_sessions = []
    real_session = repl.AgentSession

    def _capture_session(**kwargs):
        built_sessions.append(kwargs)
        return real_session(**kwargs)

    monkeypatch.setattr(repl, "AgentSession", _capture_session)
    inputs = iter(["/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl.run_common_repl(tmp_path, read_only=True, mode_label=imaging.name)

    adapter = built_sessions[0]["adapter"]
    assert isinstance(adapter, AttestedAdapter)
    assert (adapter.backend, adapter.model, adapter.strict) == (
        "pwm_qwen", "qwen3.8:27b", True)
    assert adapter.adapter is bare


def test_strict_session_holds_and_never_reaches_another_backend(
        tmp_path, monkeypatch, capsys):
    """Amendment 61 zero-fallback, instrumented where it can actually be broken.

    Every other backend is made reachable and the orchestration chain is left
    intact, so a strict session that "helpfully" retried elsewhere would show up
    as a second entry in `adapter_backends`. The complete list must stay
    `['pwm_qwen']`, and the turn must end in a visible hold rather than the
    generic "all models are temporarily unavailable" line.
    """
    from ai4science.harness import route_attestation
    from ai4science.harness.adapters import factory
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.agents.specs.imaging import AGENT as imaging_agent
    from ai4science.harness.route_attestation import StrictRouteError

    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    monkeypatch.delenv("PWM_TOKEN", raising=False)
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)

    imaging = replace(imaging_agent, name="computational-imaging")
    monkeypatch.setattr(agent_registry, "AGENT_REGISTRY", {imaging.name: imaging})
    monkeypatch.setattr(factory, "harness_available", lambda backend: True)

    hold_reason = ("strict route pwm_qwen/qwen3.8:27b is unproven: "
                   "the response carried no observed model")
    adapter_backends = []

    class Holding:
        backend = "pwm_qwen"

        def stream(self, *_args, **_kwargs):
            raise StrictRouteError(hold_reason)
            yield                                   # pragma: no cover

    def _adapter_for(backend):
        adapter_backends.append(backend)
        return Holding()

    monkeypatch.setattr(repl, "adapter_for", _adapter_for)
    monkeypatch.setattr(repl, "make_meter",
                        lambda **_kwargs: (lambda usage: None))
    inputs = iter(["reconstruct the CASSI cube", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    route_attestation.clear_holds()
    try:
        repl.run_common_repl(tmp_path, read_only=True, mode_label=imaging.name)
        out = capsys.readouterr().out

        assert adapter_backends == ["pwm_qwen"]
        assert "[harness] research task held:" in out
        assert hold_reason in out
        assert "temporarily unavailable" not in out
        assert "switching to" not in out
        held = route_attestation.holds()
        assert [(h.agent, h.backend, h.model) for h in held] == [
            ("computational-imaging", "pwm_qwen", "qwen3.8:27b")]
        assert hold_reason in held[0].reason
    finally:
        route_attestation.clear_holds()


def test_a_non_strict_session_still_walks_the_orchestration_chain(
        tmp_path, monkeypatch, capsys):
    """The other half of the rule: an ordinary worker keeps its fallback."""
    from ai4science.llm import routing
    from ai4science.harness.adapters import factory
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.events import Done, TextDelta

    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    monkeypatch.delenv("PWM_TOKEN", raising=False)
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)

    ordinary = _spec(name="ordinary", category="core")
    monkeypatch.setattr(agent_registry, "AGENT_REGISTRY", {ordinary.name: ordinary})
    monkeypatch.setattr(factory, "harness_available", lambda backend: True)
    monkeypatch.setattr(routing, "AGENT_CHAINS",
                        {"orchestration": [("anthropic", "claude-opus-5"),
                                           ("openai", "gpt-5.5")]})
    monkeypatch.setattr(repl, "_pick_brand",
                        lambda backend, model: ("anthropic", "claude-opus-5"))

    adapter_backends = []

    class Failing:
        backend = "anthropic"

        def stream(self, *_args, **_kwargs):
            raise RuntimeError("overloaded")
            yield                                   # pragma: no cover

    def _adapter_for(backend):
        adapter_backends.append(backend)
        if backend == "anthropic":
            return Failing()
        return StubAdapter([[TextDelta("second brand answered"), Done("end")]])

    monkeypatch.setattr(repl, "adapter_for", _adapter_for)
    monkeypatch.setattr(repl, "make_meter",
                        lambda **_kwargs: (lambda usage: None))
    inputs = iter(["hello", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl.run_common_repl(tmp_path, read_only=True, mode_label=ordinary.name)
    out = capsys.readouterr().out

    assert adapter_backends == ["anthropic", "openai"]
    assert "research task held" not in out
    assert "switching to gpt-5.5" in out


def test_delegated_strict_child_produces_nothing_without_proof(
        tmp_path, monkeypatch):
    """The delegation path, negatively. A child whose provider sends no
    observable metadata must produce no answer at all — the parent must not
    receive an unattested result that reads exactly like a real one."""
    from ai4science.harness.adapters.stub import StubAdapter
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.agents.specs.imaging import AGENT as imaging_agent
    from ai4science.harness.events import Done, TextDelta
    from ai4science.harness.route_attestation import StrictRouteError

    parent = _spec(name="parent", category="core")
    imaging = replace(imaging_agent, name="computational-imaging")
    monkeypatch.setattr(agent_registry, "AGENT_REGISTRY", {
        parent.name: parent, imaging.name: imaging,
    })

    child_texts = []

    def _adapter_for(_backend):
        return StubAdapter([[TextDelta("unattested answer"), Done("end")]])

    built_sessions = []
    real_session = repl.AgentSession

    def _capture_session(**kwargs):
        session = real_session(**kwargs)
        built_sessions.append((kwargs, session))
        return session

    monkeypatch.setattr(repl, "adapter_for", _adapter_for)
    monkeypatch.setattr(repl, "make_meter",
                        lambda **_kwargs: (lambda usage: None))
    monkeypatch.setattr(repl, "AgentSession", _capture_session)
    inputs = iter(["/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl.run_common_repl(tmp_path, read_only=True,
                         backend="anthropic", model="claude-opus-5",
                         mode_label=parent.name, on_text=child_texts.append)

    parent_session = built_sessions[0][1]
    with pytest.raises(StrictRouteError, match="unproven"):
        parent_session.registry.get("task").func(
            tmp_path, subagent_type=imaging.name,
            prompt="reconstruct the CASSI cube")

    assert "unattested answer" not in "".join(child_texts)


def test_model_switch_keeps_a_strict_session_guarded_at_its_spec_route(
        tmp_path, monkeypatch):
    """`/model` is the THIRD call site of `_route_adapter`, and the one no test
    reached: `_LOCKED_MENU["pwm_qwen"]` has a single entry today, so the handler
    short-circuits on "model unchanged" and the site is unreachable. Safety
    therefore rested on a menu length, not on an assertion — add a second
    `pwm_qwen` entry and a strict agent could switch onto it.

    Two things are pinned here. First, the switched session is still wrapped in
    the guard (unwrapping this site alone leaves every other test green).
    Second, the guard's REQUIRED route comes from the SPEC, not from the switch
    TARGET: a guard that took its requirement from the destination would stamp
    `attested: True` for a model the strict spec forbids. Requiring the spec's
    route means the session HOLDS on the forbidden model instead, which is the
    Amendment 61 behaviour.
    """
    from ai4science.harness.adapters import factory
    from ai4science.harness.agents import registry as agent_registry
    from ai4science.harness.agents.specs.imaging import AGENT as imaging_agent
    from ai4science.harness.route_attestation import AttestedAdapter

    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "0")
    imaging = replace(imaging_agent, name="computational-imaging")
    monkeypatch.setattr(agent_registry, "AGENT_REGISTRY", {imaging.name: imaging})
    monkeypatch.setattr(factory, "harness_available", lambda backend: True)

    # The menu length is the only thing making this site unreachable today.
    # Take it away and the site is live.
    monkeypatch.setitem(
        repl._LOCKED_MENU, "pwm_qwen",
        [("Qwen 3.8 27B", "pwm_qwen", "qwen3.8:27b"),
         ("Qwen 3.8 8B", "pwm_qwen", "qwen3.8:8b")])

    class Bare:
        backend = "pwm_qwen"

        def stream(self, *_args, **_kwargs):        # pragma: no cover
            raise AssertionError("no turn runs in this test")
            yield

    bare = Bare()
    monkeypatch.setattr(repl, "adapter_for", lambda _backend: bare)
    monkeypatch.setattr(repl, "make_meter",
                        lambda **_kwargs: (lambda usage: None))

    built_sessions = []
    real_session = repl.AgentSession

    def _capture_session(**kwargs):
        session = real_session(**kwargs)
        built_sessions.append(session)
        return session

    monkeypatch.setattr(repl, "AgentSession", _capture_session)
    inputs = iter(["/model qwen3.8:8b", "/exit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    repl.run_common_repl(tmp_path, read_only=True, mode_label=imaging.name)

    session = built_sessions[0]
    assert session.model == "qwen3.8:8b"          # the switch itself still works
    adapter = session.adapter
    assert isinstance(adapter, AttestedAdapter), (
        "a strict session must never be handed a bare adapter by /model")
    assert adapter.adapter is bare
    assert (adapter.backend, adapter.model, adapter.strict) == (
        "pwm_qwen", "qwen3.8:27b", True), (
        "the guard's required route must come from the strict SPEC, not from "
        "the model the user switched to")

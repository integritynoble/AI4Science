"""Amendment 61 "by-function" rule — instrument `repl._route_adapter` and the
four session call sites that must speak through it.

The rule is: a strict *function* (a spec with ``strict_route=True``) speaks only
through the attestation guard, and it does so at its OWN spec route, never at
whatever backend/model the caller happened to target. An ordinary agent — every
builtin spec on this branch — is untouched, byte for byte. That is the whole
point of "by function, not by account": no sarsi-worker turn is ever held by
this change.

RED-FIRST: this file is written against a contract that does NOT exist yet.
`ai4science/harness/repl.py` will gain a module-level ``_route_adapter`` and
`AgentSpec` will gain ``strict_route`` / ``default_model`` fields. Until then
these tests error out on the missing name — that is the expected RED. Each
assertion is written so it stays MEANINGFUL once the source lands (no test whose
only claim is "the attribute exists").

The guard under the hood (`route_attestation.AttestedAdapter`) is already ported
and green; this file pins the WIRING, not the guard's internals.
"""
from __future__ import annotations

import dataclasses

import pytest

from ai4science.harness import repl
from ai4science.harness.agents import registry as agent_registry
from ai4science.harness.agents.spec import AgentSpec
from ai4science.harness.events import ResponseMeta, TextDelta
from ai4science.harness.route_attestation import AttestedAdapter, StrictRouteError


# --- fixtures ---------------------------------------------------------------
# AgentSpec is frozen and requires name/tier/category/title/description. Build
# fresh instances (never mutate); strict fixtures carry the two additive fields.
_REQUIRED = dict(
    name="strict-fixture",
    tier="science",
    category="hidden",
    title="Strict Fixture",
    description="a strict-route fixture agent",
)


def _spec(**over) -> AgentSpec:
    fields = dict(_REQUIRED)
    fields.update(over)
    return AgentSpec(**fields)


def _strict_spec(**over) -> AgentSpec:
    fields = dict(
        strict_route=True,
        default_backend="pwm_qwen",
        default_model="qwen3.8:27b",
    )
    fields.update(over)
    return _spec(**fields)


class _StubInner:
    """A minimal adapter whose stream replays a fixed event list."""

    def __init__(self, events):
        self._events = list(events)

    def stream(self, messages, tools, *, model, reasoning):
        for ev in self._events:
            yield ev


# --- 1. non-strict is UNTOUCHED: same object, not merely same shape ----------
def test_non_strict_spec_returns_the_bare_adapter_object_unwrapped(monkeypatch):
    """A non-strict function must get back the EXACT object `adapter_for`
    returned — asserted with `is`. An isinstance check would pass for a guard
    too, and that would be the bug (a strict wrapper silently added to an
    ordinary agent). The sentinel makes identity unambiguous."""
    sentinel = object()
    monkeypatch.setattr(repl, "adapter_for", lambda backend: sentinel)

    result = repl._route_adapter("anthropic", "claude-opus-5", _spec())

    assert result is sentinel


# --- 2. every builtin spec on this branch is non-strict ----------------------
def test_every_builtin_spec_is_non_strict():
    """Enumerate the REAL spec registry and prove not one builtin function is
    strict on this branch — so an ordinary sarsi-worker turn is provably never
    held by this change. Reads `strict_route` off each spec directly, so it is a
    real per-spec check once the field exists, not an existence probe."""
    specs = agent_registry.reload(load_plugins=False)
    assert specs, "expected a populated builtin spec registry"

    strict = sorted(name for name, s in specs.items() if s.strict_route)
    assert strict == [], f"builtin specs unexpectedly marked strict_route: {strict}"


# --- 3. a strict spec is GUARDED (kills mT9 / mT9c at the wiring layer) -------
def test_strict_spec_is_wrapped_in_a_strict_guard(monkeypatch):
    """A strict function returns an `AttestedAdapter` that wraps the very
    adapter `adapter_for` returned, with `.strict` True."""
    inner = object()
    monkeypatch.setattr(repl, "adapter_for", lambda backend: inner)

    result = repl._route_adapter("pwm_qwen", "qwen3.8:27b", _strict_spec())

    assert isinstance(result, AttestedAdapter)
    assert result.adapter is inner
    assert result.strict is True


# --- 4. the required route comes from the SPEC, not the caller (kills mT9e) ---
def test_required_route_is_the_specs_route_not_the_callers_target(monkeypatch):
    """THE `/model` CASE — the most important test in the file. The caller's
    target is anthropic/claude-opus-5, but the strict spec pins pwm_qwen /
    qwen3.8:27b. The guard's required route MUST come from the spec: a guard
    built around the caller's destination would attest whatever `/model` chose,
    stamping attested:True on a model the strict spec forbids. mT9e is exactly
    that regression (`required = backend/model` instead of the spec)."""
    monkeypatch.setattr(repl, "adapter_for", lambda backend: object())

    strict_spec = _strict_spec(default_backend="pwm_qwen",
                               default_model="qwen3.8:27b")
    result = repl._route_adapter("anthropic", "claude-opus-5", strict_spec)

    assert isinstance(result, AttestedAdapter)
    assert result.backend == "pwm_qwen"
    assert result.model == "qwen3.8:27b"
    # ...and NOT the caller's target.
    assert result.backend != "anthropic"
    assert result.model != "claude-opus-5"


# --- 5. the guard actually HOLDS — drive the stream (kills mT9c properly) -----
def test_strict_guard_holds_the_stream_and_leaks_nothing(monkeypatch):
    """Do not stop at attribute checks: drive the returned guard's `.stream()`
    with a MISMATCHED ResponseMeta followed by a TextDelta and prove it raises
    `StrictRouteError` having released NOTHING. An attribute-only test passes
    against a guard mistakenly built with strict=False (mT9c); this one does
    not, because a strict=False guard would pass both events straight through
    and never raise."""
    mismatched = ResponseMeta(
        backend="pwm_qwen",              # backend matches the required adapter
        requested_model="qwen3.8:27b",
        observed_model="claude-opus-5",  # ...but the OBSERVED model is wrong
    )
    inner = _StubInner([mismatched, TextDelta("secret text that must not leak")])
    monkeypatch.setattr(repl, "adapter_for", lambda backend: inner)

    guard = repl._route_adapter("pwm_qwen", "qwen3.8:27b", _strict_spec())

    released = []
    with pytest.raises(StrictRouteError):
        for ev in guard.stream([], [], model="qwen3.8:27b", reasoning="medium"):
            released.append(ev)

    assert released == [], "the guard leaked events before holding"


# --- 6. all four session sites are wired (kills mT9b / mT9d) -----------------
def test_no_session_site_hands_out_a_bare_adapter():
    """Source-level instrument for mutants mT9b and mT9d: ONE call site left
    unwrapped.

    `run_common_repl` hands an adapter to a session in four places —
    `adapter=adapter_for(...)` in `_child_session_factory` and in
    `_build_session`, and `session.set_brand(adapter_for(...), ...)` in the
    `/model` handler and in the orchestration-chain fallback. Every one of them
    must route through `_route_adapter`, so NO bare form may survive anywhere in
    the file. mT9b unwraps the delegated-child site; mT9d unwraps the `/model`
    site; either would slip past a test that only exercises the interactive
    parent, which is why this reads the source directly."""
    source = open(repl.__file__, encoding="utf-8").read()

    assert "adapter=adapter_for(" not in source, (
        "a session is still constructed with a bare adapter=adapter_for(...) "
        "instead of _route_adapter(...) — mT9b territory")
    assert "set_brand(adapter_for(" not in source, (
        "set_brand(...) is still handed a bare adapter_for(...) instead of "
        "_route_adapter(...) — mT9d territory")

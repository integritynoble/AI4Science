"""Amendment 61: a strict route must PROVE itself before anything escapes.

The unit under test is a guard, and a guard on this project has been wrong three
times in the direction it existed to prevent. So these tests instrument the two
things that cannot be undone once they happen — text printed to the user and a
tool that actually ran — and they assert on ORDER, not just on the final verdict:
a stream that ends in `StrictRouteError` proves nothing if the tool call already
escaped while it was still running.

Per `adapters/base.py`, an all-`None` `ResponseMeta` means UNPROVEN, never "a
provider was contacted"; the presence of a metadata event is therefore not
evidence, and only its observed fields can settle the route.
"""
import pytest

from ai4science.harness.events import (Done, Message, ResponseMeta, TextDelta,
                                       ToolCall, Usage)
from ai4science.harness.route_attestation import AttestedAdapter, StrictRouteError

VALID = ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b", "fp_ollama", "r1")


class Stub:
    def __init__(self, events):
        self.events = events

    def stream(self, *_args, **_kwargs):
        yield from self.events


def _guarded(events, *, strict=True, sink=None, backend="pwm_qwen",
             model="qwen3.8:27b"):
    return AttestedAdapter(Stub(events), backend=backend, model=model,
                           strict=strict, evidence_sink=sink)


def _drive(guarded, messages=None):
    return list(guarded.stream(messages or [], [], model="qwen3.8:27b",
                               reasoning="low"))


# ---- the plan's two cases -------------------------------------------------

def test_strict_route_releases_output_only_after_exact_metadata():
    guarded = AttestedAdapter(
        Stub([ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b",
                           "fp_ollama", "r1"), TextDelta("ok")]),
        backend="pwm_qwen", model="qwen3.8:27b", strict=True)
    assert [event.text for event in guarded.stream([], [], model="qwen3.8:27b",
                                                   reasoning="low")
            if isinstance(event, TextDelta)] == ["ok"]


@pytest.mark.parametrize("events", [
    [TextDelta("must not escape")],
    [ResponseMeta("pwm_qwen", "qwen3.8:27b", None), TextDelta("no")],
    [ResponseMeta("pwm_qwen", "qwen3.8:27b", "other-model"), TextDelta("no")],
    [ResponseMeta("anthropic", "qwen3.8:27b", "qwen3.8:27b"), TextDelta("no")],
])
def test_strict_route_refuses_missing_or_mismatched_evidence(events):
    guarded = AttestedAdapter(Stub(events), backend="pwm_qwen",
                              model="qwen3.8:27b", strict=True)
    with pytest.raises(StrictRouteError):
        list(guarded.stream([], [], model="qwen3.8:27b", reasoning="low"))


# ---- ORDER: nothing may leave the guard before the metadata does ----------

def test_strict_route_emits_metadata_first_even_when_the_stream_does_not():
    """The buffering instrument. A pass-through guard that only *checks* at the
    end still yields `early` first — this is the assertion that catches it."""
    guarded = _guarded([TextDelta("early"), VALID, TextDelta("late")])

    events = iter(guarded.stream([], [], model="qwen3.8:27b", reasoning="low"))
    first = next(events)

    assert isinstance(first, ResponseMeta)
    assert first.observed_model == "qwen3.8:27b"
    assert [event.text for event in events] == ["early", "late"]


def test_strict_route_releases_nothing_at_all_when_evidence_never_arrives():
    guarded = _guarded([TextDelta("a"), ToolCall("c1", "bash", {}), Done("stop")])

    seen = []
    with pytest.raises(StrictRouteError):
        for event in guarded.stream([], [], model="qwen3.8:27b", reasoning="low"):
            seen.append(event)

    assert seen == []


def test_strict_route_holds_before_a_tool_call_reaches_its_tool(tmp_path):
    """A ToolCall that reaches a real tool is a side effect that cannot be
    recalled. Driven through the real `run_loop`, with a spy standing in for the
    tool and for the terminal."""
    from ai4science.harness.loop import run_loop
    from ai4science.harness.permissions import PermissionGate
    from ai4science.harness.tools.base import Registry, Tool

    ran = []
    printed = []
    registry = Registry()
    registry.add(Tool(name="spy", description="spy",
                      parameters={"type": "object", "properties": {}},
                      func=lambda workspace, **kwargs: ran.append(kwargs) or "ran"))

    guarded = _guarded([TextDelta("thinking…"),
                        ToolCall("c1", "spy", {}),
                        Done("tool_calls")])

    with pytest.raises(StrictRouteError):
        run_loop(adapter=guarded, model="qwen3.8:27b", reasoning="low",
                 history=[], workspace=tmp_path, registry=registry,
                 gate=PermissionGate(workspace=tmp_path, read_only=False,
                                     auto_yes=True),
                 on_text=printed.append, meter=lambda usage: None)

    assert ran == []
    assert printed == []


def test_strict_route_lets_a_proven_tool_call_through(tmp_path):
    """Positive control: the guard is not simply blocking every tool call."""
    from ai4science.harness.loop import run_loop
    from ai4science.harness.permissions import PermissionGate
    from ai4science.harness.tools.base import Registry, Tool

    ran = []
    registry = Registry()
    registry.add(Tool(name="spy", description="spy",
                      parameters={"type": "object", "properties": {}},
                      func=lambda workspace, **kwargs: ran.append(kwargs) or "ran"))

    class TwoTurns:
        def __init__(self):
            self.turn = 0

        def stream(self, *_args, **_kwargs):
            self.turn += 1
            if self.turn == 1:
                yield VALID
                yield ToolCall("c1", "spy", {})
            else:
                yield VALID
                yield TextDelta("done")

    guarded = AttestedAdapter(TwoTurns(), backend="pwm_qwen",
                              model="qwen3.8:27b", strict=True)
    out = run_loop(adapter=guarded, model="qwen3.8:27b", reasoning="low",
                   history=[], workspace=tmp_path, registry=registry,
                   gate=PermissionGate(workspace=tmp_path, read_only=False,
                                       auto_yes=True),
                   on_text=lambda text: None, meter=lambda usage: None)

    assert ran == [{}]
    assert out == "done"


# ---- evidence ------------------------------------------------------------

def test_evidence_sink_is_called_once_after_validation_with_observed_fields():
    sink = []
    guarded = _guarded([VALID, TextDelta("ok")], sink=sink.append)

    _drive(guarded)

    assert len(sink) == 1
    evidence = sink[0]
    assert evidence["attested"] is True
    assert evidence["backend"] == "pwm_qwen"
    assert evidence["observed_model"] == "qwen3.8:27b"
    assert evidence["system_fingerprint"] == "fp_ollama"
    assert evidence["response_id"] == "r1"
    assert evidence["required_backend"] == "pwm_qwen"
    assert evidence["required_model"] == "qwen3.8:27b"


@pytest.mark.parametrize("meta", [
    ResponseMeta("pwm_qwen", "qwen3.8:27b"),
    ResponseMeta("pwm_qwen", "qwen3.8:27b", "other-model"),
    ResponseMeta("anthropic", "qwen3.8:27b", "qwen3.8:27b"),
])
def test_no_evidence_is_produced_for_a_route_that_did_not_validate(meta):
    sink = []
    guarded = _guarded([meta, TextDelta("no")], sink=sink.append)

    with pytest.raises(StrictRouteError):
        _drive(guarded)

    assert sink == []


def test_evidence_keeps_the_requested_model_out_of_the_observed_field():
    """A requested string is not an observation. The two must stay separable in
    the record, so a later reader cannot mistake one for the other."""
    sink = []
    guarded = _guarded(
        [ResponseMeta("pwm_qwen", "qwen3.8:27b", "qwen3.8:27b", None, None)],
        sink=sink.append)

    _drive(guarded)

    assert sink[0]["requested_model"] == "qwen3.8:27b"
    assert sink[0]["observed_model"] == "qwen3.8:27b"
    assert set(sink[0]) >= {"requested_model", "observed_model"}


def test_evidence_never_promotes_a_requested_model_into_the_observed_field():
    """The fixture above asks for exactly what it observes, so writing
    `meta.requested_model` into the record's `observed_model` key is invisible
    to it — and to every other fixture in this file. Here the two differ. Task 4
    persists this record as the proof-of-compliance artifact, so a requested
    string arriving under an observed key would be a forged proof."""
    sink = []
    guarded = _guarded(
        [ResponseMeta("pwm_qwen", "qwen3.8:27b-REQUESTED", "qwen3.8:27b",
                      "fp_ollama", "r1"),
         TextDelta("ok")],
        sink=sink.append)

    _drive(guarded)

    assert sink[0]["requested_model"] == "qwen3.8:27b-REQUESTED"
    assert sink[0]["observed_model"] == "qwen3.8:27b"
    assert sink[0]["required_model"] == "qwen3.8:27b"


def test_evidence_says_which_fields_were_observed_and_which_were_configured():
    """The record must not be readable as proving more than it does. `backend`
    is the adapter's own configured label (`adapters/openai.py` writes it from
    `self.backend`), and no endpoint is attested at all."""
    sink = []
    guarded = _guarded([VALID, TextDelta("ok")], sink=sink.append)

    _drive(guarded)

    provenance = sink[0]["provenance"]
    assert provenance["observed_and_validated"] == ["observed_model"]
    assert set(provenance["observed_not_validated"]) == {
        "system_fingerprint", "response_id"}
    assert "backend" in provenance["configured_not_observed"]
    assert "backend" not in provenance["observed_and_validated"]
    assert provenance["not_attested"] == ["endpoint"]

    # Every field of the record is classified, exactly once — so a field added
    # later cannot slip into the ledger unlabelled.
    classified = [name for names in provenance.values() for name in names]
    assert len(classified) == len(set(classified))
    assert set(sink[0]) - {"attested", "provenance"} <= set(classified)


def test_an_all_none_metadata_event_is_not_proof_of_contact():
    """`base.py`: 'no credential, nothing sent', 'stream closed empty' and
    'provider omitted metadata' are the same event. None of them is evidence."""
    guarded = _guarded([ResponseMeta("pwm_qwen", "qwen3.8:27b")])

    with pytest.raises(StrictRouteError, match="unproven"):
        _drive(guarded)


def test_strict_route_fails_closed_on_a_second_metadata_event():
    guarded = _guarded([VALID, TextDelta("ok"), VALID])

    events = iter(guarded.stream([], [], model="qwen3.8:27b", reasoning="low"))
    assert isinstance(next(events), ResponseMeta)
    assert isinstance(next(events), TextDelta)
    with pytest.raises(StrictRouteError, match="second route metadata"):
        next(events)


# ---- what "matches" means, on the one dimension actually attested --------

def test_the_guard_pins_the_required_model_not_the_model_it_asked_for():
    """A comparison of the observed model against the REQUESTED one would be a
    self-consistency check — "the provider echoed back whatever we asked for" —
    and would accept any model at all on a session whose own model had drifted.
    The required model is the pin."""
    sink = []
    guarded = _guarded([ResponseMeta("pwm_qwen", "claude-opus-5",
                                     "claude-opus-5", "fp", "r1"),
                        TextDelta("must not escape")],
                       sink=sink.append)

    seen = []
    with pytest.raises(StrictRouteError, match="is not 'qwen3.8:27b'"):
        for event in guarded.stream([], [], model="claude-opus-5",
                                    reasoning="low"):
            seen.append(event)

    assert seen == []
    assert sink == []


@pytest.mark.parametrize("observed", [
    "qwen3.8:27B",             # case-folded
    " qwen3.8:27b ",           # whitespace-stripped
    "qwen3.8:27b-instruct",    # the required name is a prefix of this one
    "qwen3.8:27",              # this name is a prefix of the required one
])
def test_the_observed_model_must_match_the_required_one_exactly(observed):
    """The observed model is the SINGLE dimension this guard genuinely attests,
    so how it is compared IS the guard. Case-folding, stripping and matching in
    either substring direction each widen it to admit a different model."""
    guarded = _guarded([ResponseMeta("pwm_qwen", "qwen3.8:27b", observed),
                        TextDelta("must not escape")])

    with pytest.raises(StrictRouteError):
        _drive(guarded)


def test_a_later_valid_metadata_event_cannot_undo_an_earlier_failure():
    """A route that failed its check does not get a second attempt at passing
    it. Without the held-failure short-circuit, a wrong-model metadata event
    followed by a right-model one attests and RELEASES the buffered output."""
    sink = []
    guarded = _guarded([ResponseMeta("pwm_qwen", "qwen3.8:27b", "claude-opus-5"),
                        VALID,
                        TextDelta("must not escape")],
                       sink=sink.append)

    seen = []
    with pytest.raises(StrictRouteError, match="claude-opus-5"):
        for event in guarded.stream([], [], model="qwen3.8:27b",
                                    reasoning="low"):
            seen.append(event)

    assert seen == []
    assert sink == []


# ---- holds carry no prompt text and no credential material ---------------

def test_hold_reason_carries_no_prompt_text_or_credential_material():
    secret = "sk-live-DO-NOT-LEAK"
    prompt = "the user's private research question about ANONYMISED-PATIENT-42"
    guarded = _guarded([ResponseMeta("anthropic", "qwen3.8:27b", "claude-opus-5")])

    with pytest.raises(StrictRouteError) as excinfo:
        list(guarded.stream([Message(role="user", content=f"{prompt} {secret}")],
                            [], model="qwen3.8:27b", reasoning="low"))

    reason = excinfo.value.reason
    assert secret not in reason and prompt not in reason
    assert str(excinfo.value) == reason
    assert "pwm_qwen" in reason and "anthropic" in reason


def test_hold_reason_truncates_an_oversized_observed_model():
    guarded = _guarded([ResponseMeta("pwm_qwen", "qwen3.8:27b", "x" * 4000)])

    with pytest.raises(StrictRouteError) as excinfo:
        _drive(guarded)

    assert len(excinfo.value.reason) < 400


def test_a_recorded_hold_reason_is_capped_before_it_reaches_the_ledger():
    """`record_hold` is its OWN truncation point. A hold reason reaching it can
    come from an adapter that raised its own error, which `_short()` inside this
    module never saw — and holds are printed and persisted."""
    from ai4science.harness.route_attestation import (clear_holds, holds,
                                                      record_hold)

    clear_holds()
    try:
        hold = record_hold(agent="computational-imaging", backend="pwm_qwen",
                           model="qwen3.8:27b", reason="y" * 4000)

        assert len(hold.reason) < 500
        assert hold.reason.startswith("yyy")
        assert holds()[0].reason == hold.reason
    finally:
        clear_holds()


# ---- an inner adapter failure stays the inner adapter's failure ----------

def test_an_inner_adapter_failure_propagates_unchanged_and_releases_nothing():
    """Task 2 made the adapters emit one all-None meta and then re-raise their
    own error verbatim. The guard must not swallow that error and replace it
    with a less informative one — but it must still release nothing."""
    class Failing:
        def stream(self, *_args, **_kwargs):
            yield ResponseMeta("pwm_qwen", "qwen3.8:27b")
            raise RuntimeError("no API key configured for pwm_qwen backend")

    guarded = AttestedAdapter(Failing(), backend="pwm_qwen",
                              model="qwen3.8:27b", strict=True)

    seen = []
    with pytest.raises(RuntimeError) as excinfo:
        for event in guarded.stream([], [], model="qwen3.8:27b", reasoning="low"):
            seen.append(event)

    assert type(excinfo.value) is RuntimeError
    assert str(excinfo.value) == "no API key configured for pwm_qwen backend"
    assert seen == []


# ---- non-strict routes are untouched ------------------------------------

def test_non_strict_route_passes_everything_through_in_order():
    events = [TextDelta("a"), ResponseMeta("openai", "gpt-5.6-sol", None),
              TextDelta("b"), Usage(1, 2, 3), Done("stop")]
    guarded = _guarded(events, strict=False, backend="openai", model="gpt-5.6-sol")

    assert _drive(guarded) == events


def test_non_strict_route_forwards_metadata_to_the_sink_but_not_as_evidence():
    sink = []
    guarded = _guarded([ResponseMeta("openai", "gpt-5.6-sol", "gpt-5.6-sol"),
                        TextDelta("a")],
                       strict=False, backend="openai", model="gpt-5.6-sol",
                       sink=sink.append)

    _drive(guarded)

    assert len(sink) == 1
    assert sink[0]["attested"] is False
    assert sink[0]["observed_model"] == "gpt-5.6-sol"


def test_non_strict_route_does_not_raise_on_a_mismatched_or_absent_route():
    guarded = _guarded([ResponseMeta("openai", "gpt-5.6-sol", "something-else"),
                        TextDelta("a")],
                       strict=False, backend="openai", model="gpt-5.6-sol")

    assert [event.text for event in _drive(guarded)
            if isinstance(event, TextDelta)] == ["a"]


def test_the_guard_forwards_the_call_arguments_it_was_given():
    seen = {}

    class Recording:
        def stream(self, messages, tools, *, model, reasoning):
            seen.update(messages=messages, tools=tools, model=model,
                        reasoning=reasoning)
            yield VALID

    guarded = AttestedAdapter(Recording(), backend="pwm_qwen",
                              model="qwen3.8:27b", strict=True)
    history = [Message(role="user", content="hi")]
    list(guarded.stream(history, [], model="qwen3.8:27b", reasoning="medium"))

    assert seen["messages"] is history
    assert seen["model"] == "qwen3.8:27b"
    assert seen["reasoning"] == "medium"


def test_the_guard_reports_the_required_backend_as_its_own():
    guarded = _guarded([VALID])
    assert guarded.backend == "pwm_qwen"

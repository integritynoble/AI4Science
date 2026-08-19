"""Amendment 61: prove what can be proven before anything escapes — and say
exactly how much that is.

A strict route (research planning and delegated research execution) must run on
backend `pwm_qwen`, model `qwen3.8:27b`. This module attests ONE dimension of
that from caller-observable evidence: the model the RESPONSE reported. A module
whose job is honesty must be honest about its own reach, so, field by field:

* `observed_model` is RESPONSE-DERIVED and VALIDATED. It is read off what the
  provider sent back, and it must equal the required model exactly.
* `system_fingerprint` and `response_id` are response-derived and RECORDED, but
  nothing here validates them. They contribute nothing to the verdict.
* `backend` is a CONFIGURED adapter label — `adapters/openai.py` writes it from
  `self.backend`, not from the response — and is checked only for consistency
  with the adapter this guard was built around. It is NOT proof of which host
  answered.
* The ENDPOINT is not attested AT ALL. No base URL, no certificate, no network
  identity is examined here, and this module invents no policy for one.

So the guard's discriminating power is exactly: "the response carried model ==
qwen3.8:27b". That separates the strict route from a provider that reports its
own model id; it does not separate two hosts serving the same model id. Whether
that suffices is an owner decision, and it is deliberately not taken here.

`AttestedAdapter` sits between the harness and an adapter and BUFFERS. Nothing
semantic — no text on the user's terminal, and above all no `ToolCall` on its
way to a real tool — leaves the guard until one `ResponseMeta` has arrived and
its OBSERVED model matches the required route. A tool that has run cannot be
un-run, so the buffer, not the final verdict, is the mechanism.

Two rules follow from `adapters/base.py` and are the whole point of this module:

* An all-`None` `ResponseMeta` is UNPROVEN, never "a provider was contacted".
  "No credential, nothing sent", "the stream closed empty" and "the provider
  omitted metadata" produce the identical event, and none of them is evidence.
* A requested value is never promoted into an observed one. `route_evidence()`
  is called only after observed metadata has passed validation, and it keeps the
  requested and observed model under separate keys.

On failure the guard HOLDS: it raises `StrictRouteError` and releases nothing.
It never selects another backend — that decision does not exist here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ai4science.harness.events import ResponseMeta

#: What the guard hands an evidence sink once, and only once, per proven
#: request. A plain dict so a caller can append it straight to a JSONL ledger.
RouteEvidence = Dict[str, Any]

#: How every field of a `RouteEvidence` record came to be. It is persisted WITH
#: the record because the record travels: a reader who sees `backend` beside
#: `attested: True` must not be able to read that as proof of which host served
#: the request. `not_attested` is listed for exactly the same reason — the
#: absence of endpoint proof is a fact about this ledger, not an oversight.
EVIDENCE_PROVENANCE: Dict[str, List[str]] = {
    # Read off the provider's response AND compared against the required route.
    "observed_and_validated": ["observed_model"],
    # Read off the response, recorded only. Nothing checks these.
    "observed_not_validated": ["system_fingerprint", "response_id"],
    # Local configuration copied into the record. `backend` is the adapter's own
    # label, checked for consistency with this guard — never host proof.
    "configured_not_observed": ["backend", "requested_model", "transport",
                                "required_backend", "required_model"],
    # Named so the gap is explicit rather than merely absent.
    "not_attested": ["endpoint"],
}

#: Cap on any provider-supplied string quoted back in a hold reason. Holds are
#: printed and persisted, so they stay short and carry no unbounded input.
_MAX_QUOTED = 120

#: Cap on a whole recorded hold reason (which already quotes at most one
#: provider string, capped above).
_MAX_HOLD_REASON = 400


class StrictRouteError(RuntimeError):
    """A strict route could not be proven from observed response metadata.

    `reason` is safe to print and to persist: it names backends and models only,
    and never carries prompt text or credential material.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _short(value: Any, limit: int = _MAX_QUOTED) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def route_evidence(meta: ResponseMeta, *, required_backend: str,
                   required_model: str) -> RouteEvidence:
    """Build the attested record. Callable ONLY after `_validate` passed.

    The record carries `provenance` so it cannot be misread later: it names the
    one field that was observed AND validated, the fields that were merely
    observed, the fields that are configuration, and the endpoint, which is not
    attested at all.
    """
    return {
        "attested": True,
        "provenance": {key: list(names)
                       for key, names in EVIDENCE_PROVENANCE.items()},
        "backend": meta.backend,
        "requested_model": meta.requested_model,
        "observed_model": meta.observed_model,
        "system_fingerprint": meta.system_fingerprint,
        "response_id": meta.response_id,
        "transport": meta.transport,
        "required_backend": required_backend,
        "required_model": required_model,
    }


def _observation_record(meta: ResponseMeta) -> Dict[str, Any]:
    """What a NON-strict route forwards to a sink: an observation, not evidence.
    `attested` is False and stays False — nothing validated it."""
    return {
        "attested": False,
        "backend": meta.backend,
        "requested_model": meta.requested_model,
        "observed_model": meta.observed_model,
        "system_fingerprint": meta.system_fingerprint,
        "response_id": meta.response_id,
        "transport": meta.transport,
    }


class AttestedAdapter:
    """Adapter-shaped guard. Same `stream()` signature as any `AgentAdapter`."""

    def __init__(self, adapter, backend: str, model: str, strict: bool,
                 evidence_sink=None) -> None:
        self.adapter = adapter
        self.backend = backend
        self.model = model
        self.strict = bool(strict)
        self.evidence_sink = evidence_sink

    # -- validation ---------------------------------------------------------
    def _validate(self, meta: ResponseMeta) -> Optional[str]:
        """Return None when the route is proven, else a safe hold reason."""
        head = f"strict route {self.backend}/{self.model} is unproven"
        if meta.backend != self.backend:
            return (f"{head}: metadata came from adapter backend "
                    f"{_short(meta.backend)!r}")
        # Absence of observation is not proof: an all-None ResponseMeta means
        # the adapter reached its sequencing point, nothing more.
        if meta.observed_model is None:
            return f"{head}: the response carried no observed model"
        if meta.observed_model != self.model:
            return (f"{head}: observed model {_short(meta.observed_model)!r} "
                    f"is not {self.model!r}")
        return None

    def _emit(self, record) -> None:
        if self.evidence_sink is not None:
            self.evidence_sink(record)

    # -- streaming ----------------------------------------------------------
    def stream(self, messages, tools, *, model: str,
               reasoning: str) -> Iterator[object]:
        inner = self.adapter.stream(messages, tools, model=model,
                                    reasoning=reasoning)
        if not self.strict:
            yield from self._passthrough(inner)
            return
        yield from self._attested(inner)

    def _passthrough(self, inner) -> Iterator[object]:
        for event in inner:
            if isinstance(event, ResponseMeta):
                self._emit(_observation_record(event))
            yield event

    def _attested(self, inner) -> Iterator[object]:
        buffered: List[object] = []
        attested = False
        failure: Optional[str] = None

        for event in inner:
            if isinstance(event, ResponseMeta):
                if attested:
                    # The base contract is one ResponseMeta per request. A
                    # second one means the stream is not the shape the proof
                    # was read from, so the proof no longer covers it.
                    raise StrictRouteError(
                        f"strict route {self.backend}/{self.model} saw a second "
                        f"route metadata event in one request")
                if failure is not None:
                    continue          # already held; a later event cannot undo it
                failure = self._validate(event)
                if failure is not None:
                    # Keep draining so an adapter that raises its OWN error
                    # after the metadata (Task 2's documented hold shape) can
                    # still surface it verbatim. Nothing is released either way.
                    buffered.clear()
                    continue
                attested = True
                self._emit(route_evidence(event, required_backend=self.backend,
                                          required_model=self.model))
                yield event
                for held in buffered:
                    yield held
                buffered.clear()
                continue
            if attested:
                yield event
            elif failure is None:
                buffered.append(event)

        if not attested:
            raise StrictRouteError(failure or (
                f"strict route {self.backend}/{self.model} is unproven: no "
                f"response metadata was observed"))


# ---------------------------------------------------------------------------
# Holds. A strict session that cannot prove its route records one and stops; it
# does not choose another backend. Task 4 bridges these onto the Sarsi task
# lifecycle — this is the in-process ledger they are read from.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RouteHold:
    agent: str
    backend: str
    model: str
    reason: str


_HOLDS: List[RouteHold] = []


def record_hold(*, agent: str, backend: str, model: str,
                reason: str) -> RouteHold:
    hold = RouteHold(agent=agent, backend=backend, model=model,
                     reason=_short(reason, _MAX_HOLD_REASON))
    _HOLDS.append(hold)
    return hold


def holds() -> Tuple[RouteHold, ...]:
    return tuple(_HOLDS)


def clear_holds() -> None:
    _HOLDS.clear()

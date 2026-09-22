"""The evaluator that scores a run lives outside the agent's world.

Phase 5 of the reliable-terminal plan says the store must be sealed against the
optimizer. An evaluator sharing the agent's process, cwd, mounts, tools, logs and
network is an evaluator the agent can talk its way past: edit the artefacts after
they are read, edit the verdict after it is written, or simply reach the score.

The pieces:

``handoff``   a read-only snapshot of the run's artefacts plus a manifest of
              per-file digests, sealed into the evaluator's store at handoff time
              so the agent cannot rewrite the record of what it handed over.
``store``     the evaluator's own directory: mode ``0o000`` between evaluations,
              an HMAC key the agent never sees, verdicts sealed with it, and a
              named incident log.
``evaluator`` the child entry point (``python -m ...isolated_eval.evaluator``):
              its own cwd, a scrubbed environment, no network.
``runner``    the trusted launcher, and ``IsolatedEvaluatorVerifier`` which drops
              into ``ai4science.harness.runtime.pev.run_task`` as a ``Verifier``.

Every tampering path is *caught and named*: see ``INCIDENT_KINDS``.
"""

from .errors import BoundaryViolation, NetworkDenied, TamperDetected
from .handoff import Handoff, seal_handoff, verify_handoff
from .store import INCIDENT_KINDS, EvaluatorStore
from .runner import IsolatedEvaluator, IsolatedEvaluatorVerifier

__all__ = [
    "BoundaryViolation", "NetworkDenied", "TamperDetected",
    "Handoff", "seal_handoff", "verify_handoff",
    "EvaluatorStore", "INCIDENT_KINDS",
    "IsolatedEvaluator", "IsolatedEvaluatorVerifier",
]

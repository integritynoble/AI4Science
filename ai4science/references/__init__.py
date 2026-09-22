"""Reference records: what a later run is compared against (plan A00, A01).

A00 asks for a **pinned model revision**; A01 asks for **basic and strong
references, a frozen task contract and a local fixture, with negative controls
and a cost-metering pilot**. Both are the same object — a record of one run of
one named model revision against one frozen task, with its metered cost, sealed
by hash so that a later run cannot quietly edit what it is being judged against.

The distinction this package insists on, because A05 ("validation against strong
reference") makes it load-bearing:

  * a **candidate** is what a model produced. Nothing has checked it.
  * a **reference** is a candidate that something outside the model has
    checked — the fixture's own answer key, or a named person.

A model's output is never a reference on the strength of the model being large.
Validating a candidate against an unchecked bigger model's output is comparing
two guesses, so `record_run` always writes `status="candidate"` and promotion is
a separate, recorded act (`promote`). See `docs/A00_MODEL_PIN_PROPOSAL.md` and
`docs/REFERENCE_RECORDS.md`.
"""
from __future__ import annotations

from ai4science.references.store import (  # noqa: F401
    ReferenceRecord,
    ReferenceStore,
    SealBroken,
    seal_of,
)
# Exported as `compare_run`, not `compare`: re-exporting the function under its
# own name would shadow the `ai4science.references.compare` submodule on this
# package, and `from ai4science.references import compare` would then silently
# hand back a function where a caller asked for a module.
from ai4science.references.compare import (  # noqa: F401
    Comparison,
    compare as compare_run,
)
from ai4science.references.task import FrozenTask, LDCT_JUDGE_TASK  # noqa: F401

__all__ = [
    "ReferenceRecord",
    "ReferenceStore",
    "SealBroken",
    "seal_of",
    "Comparison",
    "compare_run",
    "FrozenTask",
    "LDCT_JUDGE_TASK",
]

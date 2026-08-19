#!/usr/bin/env python3
"""Amendment 61 mutation battery — durable, in-repo, runnable.

WHY THIS FILE EXISTS
--------------------
Every earlier round's mutants lived in `/tmp` and were thrown away. Two real
survivors (`mD1-mid`, `mT9d`) therefore went unnoticed for a whole round, and
five reviewer mutants had to be reconstructed from prose because their patches
existed nowhere. A mutation result that cannot be re-run is not evidence; it is
a claim. This file makes the battery a fact a later session can reproduce.

WHAT IT DOES
------------
Copies the repository into a throwaway directory (the worktree is NEVER
mutated), then for each mutant: applies an EXACT textual patch, runs the
Amendment 61 baseline suites against the copy, records how many tests failed,
and reverts. It compares each result with the manifest below, which records the
expected outcome INCLUDING the known survivors, so a survivor is a visible,
diffable fact rather than something a reviewer has to rediscover.

RUN
---
    python3 tests/mutation/amendment_61_mutation_battery.py            # all
    python3 tests/mutation/amendment_61_mutation_battery.py mT9d mD1-mid
    python3 tests/mutation/amendment_61_mutation_battery.py --list

Exit status is 0 when every mutant matched its manifest entry, 1 otherwise.
Only killed-vs-survived decides the exit status — with one guard: a mutant run
that exits non-zero while NO test failure was parsed is never counted as a
kill. That is pytest erroring out during import or collection, so no test
asserted anything about the contract; it is reported as `COLLECTION ERROR` and
fails the run. `expect_failures` records how
many baseline tests the mutant took down when it was last measured; a change
there is reported as "count drift" and is expected whenever a suite grows, but
a mutant whose count collapses toward 1 is worth a look — it usually means the
instrument that used to catch it broadly has been narrowed.

No network is contacted; the suites it runs are entirely fixture-driven.

PATCH PROVENANCE — read this before trusting an id
--------------------------------------------------
`provenance` on each mutant says where its patch text comes from:

* `recorded`     — the patch was written down when the mutant was first run.
* `reconstructed`— the mutant id appears in an earlier round's prose, but the
                   patch itself was never recorded anywhere on disk. The patch
                   here was rebuilt from the described defect and targets the
                   same surface; it is NOT guaranteed byte-identical to what the
                   original reviewer ran.
* `unrecovered`  — listed in `UNRECOVERED` at the bottom: an id from earlier
                   prose whose defect was never described precisely enough to
                   rebuild. These are gaps, and they are named so they stay
                   visible.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

REPO = Path(__file__).resolve().parents[2]

#: The Amendment 61 baseline suites. A mutant counts as KILLED when any of them
#: fails. Deliberately not the whole `tests/` tree: these are the suites that
#: claim to instrument the contract, so a mutant killed only by an unrelated
#: suite is not evidence that the contract is instrumented.
BASELINE = [
    "tests/test_route_attestation.py",
    "tests/test_harness_repl_strict_route.py",
    "tests/test_response_metadata.py",
    "tests/test_llm_proxy.py",
    "tests/test_harness_adapter_openai.py",
    "tests/test_harness_adapter_coverage.py",
    "tests/imaging/test_llm_planner.py",
    "tests/test_harness_repl_resilience.py",
]

COPY_INCLUDE = ["ai4science", "tests", "pwm_core", "pyproject.toml"]


@dataclass
class Mutant:
    id: str
    surface: str
    defect: str
    path: str
    old: str
    new: str
    expect_killed: bool
    expect_failures: Optional[int] = None
    provenance: str = "recorded"
    note: str = ""


G = "ai4science/harness/route_attestation.py"
O = "ai4science/harness/adapters/openai.py"
P = "ai4science/harness/adapters/proxy.py"
GW = "ai4science/harness/llm_gateway.py"
R = "ai4science/harness/repl.py"
PL = "ai4science/harness/agents/imaging/llm/planner.py"
OC = "ai4science/llm/openai_compat.py"
SP = "ai4science/harness/agents/specs/imaging.py"

MUTANTS: List[Mutant] = [
    # ---------------------------------------------------------------- Task 2
    Mutant(
        id="mA",
        surface="openai adapter metadata collection",
        defect="absorb provider metadata from the FIRST chunk only, so fields "
               "split across a prelude are lost",
        path=O,
        old="""            for ch in chunks:
                if phase is _MetaPhase.COLLECTING:
                    absorb_metadata(ch)""",
        new="""            first = True
            for ch in chunks:
                if first:
                    absorb_metadata(ch)
                first = False""",
        expect_killed=True,
        expect_failures=2,
    ),
    Mutant(
        id="mB1",
        surface="openai adapter clean-exhaustion emit",
        defect="a stream that closes with no semantic event emits no ResponseMeta",
        path=O,
        old="""        if phase is _MetaPhase.COLLECTING:
            yield metadata_event()

    def stream(""",
        new="""
    def stream(""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mB2",
        surface="openai adapter exception-path emit",
        defect="a failure before the first semantic event propagates with no "
               "ResponseMeta, leaving a strict guard nothing to read",
        path=O,
        old="""        except Exception:
            if phase is _MetaPhase.COLLECTING:
                phase = _MetaPhase.EMITTED
                yield metadata_event()
            raise""",
        new="""        except Exception:
            raise""",
        expect_killed=True,
        expect_failures=5,
    ),
    Mutant(
        id="mC1",
        surface="proxy duplicate-metadata guard",
        defect="the proxy accepts a second metadata event instead of failing closed",
        path=P,
        old="""                        if kind == "meta":
                            if phase is _ProxyMetaPhase.EMITTED:
                                raise RuntimeError("duplicate metadata event from proxy")""",
        new="""                        if kind == "meta":
                            if False:
                                raise RuntimeError("duplicate metadata event from proxy")""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mC2",
        surface="proxy semantic-before-metadata guard",
        defect="the proxy releases a semantic event that arrived before any "
               "metadata — the exact breach mD1-mid causes on the wire",
        path=P,
        old="""                        if phase is _ProxyMetaPhase.WAITING:
                            raise RuntimeError(
                                "proxy semantic event before metadata")
                        yield ev""",
        new="""                        yield ev""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mC3",
        surface="proxy malformed-JSON guard",
        defect="a line that is not JSON is silently skipped instead of failing "
               "the stream closed",
        path=P,
        old="""                        except (TypeError, ValueError) as exc:
                            raise RuntimeError(
                                f"malformed proxy event: invalid JSON: {exc}") from exc""",
        new="""                        except (TypeError, ValueError):
                            continue""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mE1",
        surface="proxy bill-before-metadata guard",
        defect="a billing line before metadata is ignored, so the turn is "
               "charged with the route still unproven and the stream reads on",
        path=P,
        old="""                        if kind == "bill":
                            if phase is _ProxyMetaPhase.WAITING:
                                raise RuntimeError(
                                    "proxy stream ended without valid metadata")
                            continue            # billing handled server-side""",
        new="""                        if kind == "bill":
                            continue            # billing handled server-side""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mF1",
        surface="openai adapter observed-vs-requested separation",
        defect="the REQUESTED model is promoted into the OBSERVED field — the "
               "single change that makes every attestation trivially pass",
        path=O,
        old="""                observed_model=observed["observed_model"],""",
        new="""                observed_model=observed["observed_model"] or requested_model,""",
        expect_killed=True,
        expect_failures=7,
    ),
    Mutant(
        id="mF2",
        surface="openai_compat.chat_with_meta",
        defect="the same requested-into-observed promotion on the non-streaming path",
        path=OC,
        old="""        observed_model=response.get("model"),""",
        new="""        observed_model=response.get("model") or requested_model,""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mG1",
        surface="proxy metadata forwarding",
        defect="the proxy rewrites the SERVER's backend and observed model from "
               "the LOCAL request, manufacturing agreement",
        path=P,
        old="""                            yield replace(ev, transport="proxy")""",
        new="""                            yield replace(ev, transport="proxy",
                                          backend=self.backend,
                                          observed_model=model)""",
        expect_killed=True,
        expect_failures=3,
    ),
    Mutant(
        id="mM1",
        surface="openai adapter lazy imports",
        defect="the lazy imports move back into the generator body, so an "
               "unimportable dependency fails OUTSIDE _parse_stream's "
               "sequencing and emits no ResponseMeta",
        path=O,
        old="""            from ai4science.harness import transport
            from ai4science.harness.adapters._dotdict import dot
            if not (c and c.api_key):""",
        new="""            if not (c and c.api_key):""",
        expect_killed=True,
        expect_failures=1,
        note="paired with the injected module-body imports below",
    ),
    Mutant(
        id="mD1",
        surface="gateway fallback metadata (ALL three sites)",
        defect="the gateway never synthesises a metadata line, so any adapter "
               "that emits none produces a wire with no `meta` at all",
        path=GW,
        old="""                if phase is _GatewayMetaPhase.WAITING:
                    phase = _GatewayMetaPhase.SENT
                    yield fallback_meta_line()
                if w.get("t") == "usage":""",
        new="""                if w.get("t") == "usage":""",
        expect_killed=True,
        expect_failures=3,
        note="applied together with mD1-tail and mD1-exc by the runner",
    ),
    Mutant(
        id="mD1-mid",
        surface="gateway MID-STREAM fallback metadata emit only",
        defect="only the mid-stream emit is deleted. The wire becomes "
               "['text','tool','usage','done','meta','bill'] and the real "
               "ProxyAdapter raises 'proxy semantic event before metadata'. "
               "Load-bearing on EVERY request for anthropic/gemini/codex/stub, "
               "which emit no ResponseMeta of their own.",
        path=GW,
        old="""                if phase is _GatewayMetaPhase.WAITING:
                    phase = _GatewayMetaPhase.SENT
                    yield fallback_meta_line()
                if w.get("t") == "usage":""",
        new="""                if w.get("t") == "usage":""",
        expect_killed=True,
        expect_failures=1,
        note="SURVIVED until 2026-08-18; killed by "
             "test_gateway_no_metadata_adapter_emits_meta_before_first_semantic_event",
    ),
    # ---------------------------------------------------------------- Task 3
    Mutant(
        id="mT1",
        surface="AttestedAdapter buffering",
        defect="release every event as it arrives and decide the verdict only "
               "at end of stream — the tool has already run by then",
        path=G,
        old="""            elif failure is None:
                buffered.append(event)""",
        new="""            elif failure is None:
                yield event""",
        expect_killed=True,
        expect_failures=4,
    ),
    Mutant(
        id="mT2",
        surface="AttestedAdapter._validate absent-observation rule",
        defect="an all-None ResponseMeta counts as proof that a provider answered",
        path=G,
        old="""        if meta.observed_model is None:
            return f"{head}: the response carried no observed model"
""",
        new="""        if meta.observed_model is None:
            return None
""",
        expect_killed=True,
        expect_failures=4,
    ),
    Mutant(
        id="mT3",
        surface="AttestedAdapter._validate backend check",
        defect="metadata from any adapter backend is accepted",
        path=G,
        old="""        if meta.backend != self.backend:
            return (f"{head}: metadata came from adapter backend "
                    f"{_short(meta.backend)!r}")""",
        new="""        if False:
            return (f"{head}: metadata came from adapter backend "
                    f"{_short(meta.backend)!r}")""",
        expect_killed=True,
        expect_failures=3,
    ),
    Mutant(
        id="mT4",
        surface="AttestedAdapter._validate model equality",
        defect="any observed model satisfies the strict route",
        path=G,
        old="""        if meta.observed_model != self.model:
            return (f"{head}: observed model {_short(meta.observed_model)!r} "
                    f"is not {self.model!r}")""",
        new="""        if False:
            return (f"{head}: observed model {_short(meta.observed_model)!r} "
                    f"is not {self.model!r}")""",
        expect_killed=True,
        expect_failures=10,
    ),
    Mutant(
        id="mT5",
        surface="AttestedAdapter evidence sink",
        defect="no evidence record is ever emitted — the route is proven and "
               "leaves no trace",
        path=G,
        old="""    def _emit(self, record) -> None:
        if self.evidence_sink is not None:
            self.evidence_sink(record)""",
        new="""    def _emit(self, record) -> None:
        return None""",
        expect_killed=True,
        expect_failures=5,
    ),
    Mutant(
        id="mT6",
        surface="REPL strict hold branch",
        defect="a strict agent's failed turn walks the orchestration chain like "
               "any other agent — the zero-fallback breach itself",
        path=R,
        old="""            if getattr(active_spec, "strict_route", False):
                from ai4science.harness import route_attestation""",
        new="""            if False:
                from ai4science.harness import route_attestation""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mT7",
        surface="AttestedAdapter tool-call containment",
        defect="a ToolCall is released before validation — the irreversible case",
        path=G,
        old="""            if attested:
                yield event
            elif failure is None:""",
        new="""            if attested or type(event).__name__ == "ToolCall":
                yield event
            elif failure is None:""",
        expect_killed=True,
        expect_failures=1,
    ),
    Mutant(
        id="mT8",
        surface="LLMImagingPlanner strict re-raise",
        defect="the strict planner swallows the adapter/attestation failure and "
               "falls back to deterministic GAP-TV, which is indistinguishable "
               "in every artefact from research that really happened",
        path=PL,
        old="""        except Exception:
            if self.strict:
                raise
            return None""",
        new="""        except Exception:
            return None""",
        expect_killed=True,
        expect_failures=3,
    ),
    Mutant(
        id="mT9",
        surface="REPL _route_adapter — guard removed entirely",
        defect="a strict session is handed the bare adapter",
        path=R,
        old="""        adapter = adapter_for(backend)
        if not getattr(spec, "strict_route", False):
            return adapter""",
        new="""        adapter = adapter_for(backend)
        if True:
            return adapter""",
        expect_killed=True,
        expect_failures=4,
    ),
    Mutant(
        id="mT9b",
        surface="REPL delegated-child call site",
        defect="only the DELEGATED child session is unwrapped; the parent stays "
               "guarded, so the interactive path looks correct",
        path=R,
        old="""            adapter=_route_adapter(child_backend, child_model, spec),""",
        new="""            adapter=adapter_for(child_backend),""",
        expect_killed=True,
        expect_failures=2,
        provenance="reconstructed",
    ),
    Mutant(
        id="mT9c",
        surface="REPL _route_adapter strict flag",
        defect="the guard is built with strict=False, so it becomes a pure "
               "pass-through that still passes an isinstance check",
        path=R,
        old="""        return AttestedAdapter(adapter, backend=required_backend,
                               model=required_model, strict=True)""",
        new="""        return AttestedAdapter(adapter, backend=required_backend,
                               model=required_model, strict=False)""",
        expect_killed=True,
        expect_failures=4,
        provenance="reconstructed",
    ),
    Mutant(
        id="mT9d",
        surface="REPL /model switch call site",
        defect="only the `/model` call site is unwrapped. Unreachable today "
               "solely because _LOCKED_MENU['pwm_qwen'] has ONE entry and the "
               "handler short-circuits on 'model unchanged' — safety resting on "
               "a menu length, not an assertion",
        path=R,
        old="""                    session.set_brand(
                        _route_adapter(new_backend, new_model, active_spec),
                        new_model, new_backend)""",
        new="""                    session.set_brand(
                        adapter_for(new_backend),
                        new_model, new_backend)""",
        expect_killed=True,
        expect_failures=1,
        note="SURVIVED until 2026-08-18; killed by "
             "test_model_switch_keeps_a_strict_session_guarded_at_its_spec_route",
    ),
    Mutant(
        id="mT9e",
        surface="REPL _route_adapter required-route source",
        defect="the guard's required route is taken from the CALLER's target "
               "instead of the strict SPEC, so `/model` onto a second pwm_qwen "
               "menu entry would stamp attested:True on a forbidden model",
        path=R,
        old="""        required_backend = getattr(spec, "default_backend", None) or backend
        required_model = getattr(spec, "default_model", None) or model""",
        new="""        required_backend = backend
        required_model = model""",
        expect_killed=True,
        expect_failures=1,
        note="this is the pre-2026-08-18 behaviour; kept as a regression mutant",
    ),
    Mutant(
        id="mT10",
        surface="AttestedAdapter as a whole",
        defect="the guard degrades to a logger: it releases everything and "
               "never holds",
        path=G,
        old="""        if not self.strict:
            yield from self._passthrough(inner)
            return
        yield from self._attested(inner)""",
        new="""        yield from self._passthrough(inner)
        return""",
        expect_killed=True,
        expect_failures=26,
    ),
    Mutant(
        id="mX2",
        surface="_observation_record honesty",
        defect="a NON-strict observation is recorded as attested:True, so an "
               "unvalidated record reads in the ledger exactly like a proven one",
        path=G,
        old="""    return {
        "attested": False,
        "backend": meta.backend,""",
        new="""    return {
        "attested": True,
        "backend": meta.backend,""",
        expect_killed=True,
        expect_failures=1,
        provenance="reconstructed",
    ),
    Mutant(
        id="mX3",
        surface="route_evidence provenance key",
        defect="the provenance map is dropped from the record, so a reader who "
               "sees `backend` beside attested:True can read it as host proof",
        path=G,
        old="""        "attested": True,
        "provenance": {key: list(names)
                       for key, names in EVIDENCE_PROVENANCE.items()},""",
        new="""        "attested": True,""",
        expect_killed=True,
        expect_failures=1,
        provenance="reconstructed",
    ),
    Mutant(
        id="mX6",
        surface="AttestedAdapter second-metadata guard",
        defect="a second ResponseMeta in one request is ignored rather than "
               "failing closed, so the proof no longer covers the stream shape "
               "it was read from",
        path=G,
        old="""                if attested:
                    # The base contract is one ResponseMeta per request. A
                    # second one means the stream is not the shape the proof
                    # was read from, so the proof no longer covers it.
                    raise StrictRouteError(
                        f"strict route {self.backend}/{self.model} saw a second "
                        f"route metadata event in one request")""",
        new="""                if attested:
                    continue""",
        expect_killed=True,
        expect_failures=1,
        provenance="reconstructed",
    ),
    Mutant(
        id="mX7",
        surface="_short truncation of provider strings",
        defect="a provider-supplied string is quoted back into a hold reason "
               "unbounded; holds are printed and persisted",
        path=G,
        old="""def _short(value: Any, limit: int = _MAX_QUOTED) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…\"""",
        new="""def _short(value: Any, limit: int = _MAX_QUOTED) -> str:
    return str(value)""",
        expect_killed=True,
        expect_failures=2,
        provenance="reconstructed",
    ),
    Mutant(
        id="mX8",
        surface="AttestedAdapter already-held latch",
        defect="a hold is not sticky: a later ResponseMeta re-validates and can "
               "release the stream that a previous one already held",
        path=G,
        old="""                if failure is not None:
                    continue          # already held; a later event cannot undo it""",
        new="""                if False:
                    continue          # already held; a later event cannot undo it""",
        expect_killed=True,
        expect_failures=1,
        provenance="reconstructed",
    ),
    Mutant(
        id="mX8b",
        surface="AttestedAdapter end-of-stream hold",
        defect="an unproven stream ends QUIETLY instead of raising — the caller "
               "sees a successful empty turn, not a hold",
        path=G,
        old="""        if not attested:
            raise StrictRouteError(failure or (""",
        new="""        if not attested and False:
            raise StrictRouteError(failure or (""",
        expect_killed=True,
        expect_failures=20,
        provenance="reconstructed",
    ),
    Mutant(
        id="mP1",
        surface="LLMImagingPlanner strict flag storage",
        defect="the constructor accepts strict= and ignores it",
        path=PL,
        old="""        self.strict = bool(strict)""",
        new="""        self.strict = False""",
        expect_killed=True,
        expect_failures=3,
        provenance="reconstructed",
    ),
    Mutant(
        id="mP2",
        surface="LLMImagingPlanner strict default",
        defect="strict defaults to True, withdrawing the deterministic fallback "
               "from ordinary non-strict use",
        path=PL,
        old="""                 reasoning: str = "medium", solvers=None, strict: bool = False):""",
        new="""                 reasoning: str = "medium", solvers=None, strict: bool = True):""",
        expect_killed=True,
        expect_failures=1,
        provenance="reconstructed",
    ),
    Mutant(
        id="mP3",
        surface="LLMImagingPlanner.next_step",
        defect="the silent fallback is re-introduced one level up: next_step "
               "swallows what _select correctly re-raised",
        path=PL,
        old="""            key = self._select(state)""",
        new="""            try:
                key = self._select(state)
            except Exception:
                key = None""",
        expect_killed=True,
        expect_failures=3,
        provenance="reconstructed",
    ),
    Mutant(
        id="mP4",
        surface="computational-imaging AgentSpec",
        defect="the imaging agent is no longer marked strict_route, so nothing "
               "downstream is strict at all",
        path=SP,
        old="""    strict_route=True,""",
        new="""    strict_route=False,""",
        expect_killed=True,
        expect_failures=5,
        provenance="reconstructed",
    ),
]

#: Mutants that need more than one hunk.
EXTRA_HUNKS = {
    "mD1": [
        (GW,
         """            if phase is _GatewayMetaPhase.WAITING:
                phase = _GatewayMetaPhase.SENT
                yield fallback_meta_line()
            yield json.dumps({"t": "text",""",
         """            yield json.dumps({"t": "text","""),
        (GW,
         """        if phase is _GatewayMetaPhase.WAITING:
            phase = _GatewayMetaPhase.SENT
            yield fallback_meta_line()
        # final billing line""",
         """        # final billing line"""),
    ],
    "mM1": [
        (O,
         """        c = self.creds""",
         """        from ai4science.harness import transport
        from ai4science.harness.adapters._dotdict import dot
        c = self.creds"""),
    ],
}

#: Ids that appear in earlier rounds' prose with no recoverable patch. They are
#: named so the gap stays visible instead of reading as complete coverage.
UNRECOVERED = {
    "mT6b": "a variant of mT6 (strict REPL hold branch); defect never written down",
    "mX1": "route_attestation honesty surface; defect never written down",
    "mX4": "route_attestation honesty surface; defect never written down",
    "mX4b": "variant of mX4; defect never written down",
    "mX5": "route_attestation honesty surface; defect never written down",
}


# ---------------------------------------------------------------------------
_SUMMARY = re.compile(r"(\d+) failed")


def _copy_repo(dest: Path) -> None:
    for name in COPY_INCLUDE:
        src = REPO / name
        if not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dest / name, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", ".pytest_cache"))
        else:
            shutil.copy2(src, dest / name)


def _hunks(m: Mutant):
    return [(m.path, m.old, m.new)] + list(EXTRA_HUNKS.get(m.id, []))


def _apply(root: Path, m: Mutant, originals: dict) -> None:
    for path, old, new in _hunks(m):
        target = root / path
        text = target.read_text()
        if path not in originals:
            originals[path] = text
        if text.count(old) != 1:
            raise SystemExit(
                f"{m.id}: patch anchor matched {text.count(old)} times in "
                f"{path} — the battery is STALE, fix the anchor before "
                f"trusting any result")
        target.write_text(text.replace(old, new))


def _revert(root: Path, originals: dict) -> None:
    for path, text in originals.items():
        (root / path).write_text(text)


def _run(root: Path) -> tuple:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q",
         "-p", "no:cacheprovider", "--no-header", *BASELINE],
        cwd=root, capture_output=True, text=True, env=env,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    hit = _SUMMARY.search(proc.stdout)
    return proc.returncode, (int(hit.group(1)) if hit else 0), tail


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ids", nargs="*", help="mutant ids to run (default: all)")
    ap.add_argument("--list", action="store_true", help="list the manifest")
    args = ap.parse_args()

    if args.list:
        for m in MUTANTS:
            flag = "kill" if m.expect_killed else "SURVIVES"
            print(f"{m.id:10s} {flag:9s} {m.provenance:14s} {m.surface}")
        for mid, why in UNRECOVERED.items():
            print(f"{mid:10s} {'UNRECOVERED':9s} {'':14s} {why}")
        return 0

    selected = [m for m in MUTANTS if not args.ids or m.id in args.ids]
    unknown = set(args.ids) - {m.id for m in MUTANTS}
    if unknown:
        print(f"unknown mutant id(s): {sorted(unknown)}")
        return 1

    tmp = Path(tempfile.mkdtemp(prefix="a61-battery-"))
    root = tmp / "tree"
    root.mkdir()
    try:
        _copy_repo(root)
        code, failures, tail = _run(root)
        print(f"baseline (unmutated copy): rc={code} {tail}")
        if code != 0:
            print("BASELINE IS NOT GREEN — every result below is meaningless.")
            return 1

        mismatches = []
        drifted = []
        for m in selected:
            originals: dict = {}
            try:
                _apply(root, m, originals)
                code, failures, tail = _run(root)
            finally:
                _revert(root, originals)
            killed = code != 0
            # A non-zero exit with ZERO parsed test failures is NOT a kill:
            # pytest itself errored out — an import or collection error — so no
            # test asserted anything about the contract. Counting that as a
            # kill would let a mutant that merely breaks the module read as
            # evidence the instrument caught it, which is the very failure
            # this battery exists to detect, one level up. Always a mismatch.
            errored = killed and failures == 0
            ok = killed == m.expect_killed and not errored
            drift = (m.expect_failures is not None
                     and failures != m.expect_failures)
            status = ("ERROR" if errored
                      else "KILLED" if killed else "SURVIVED")
            mark = "ok " if ok else "MISMATCH"
            print(f"{mark} {m.id:10s} {status:8s} failures={failures:<3d} "
                  f"expected={'killed' if m.expect_killed else 'survives'}"
                  f"{'' if m.expect_failures is None else '/' + str(m.expect_failures)}"
                  f"{'  <- count drift' if drift else ''}"
                  f"  [{m.provenance}]  {tail}")
            if errored:
                print(f"    {m.id}: COLLECTION ERROR — not an assertion kill "
                      f"(pytest exited {code} with no test failure reported; "
                      f"the mutant broke import or collection, so nothing "
                      f"asserted the contract)")
            if drift:
                drifted.append(m.id)
            if not ok:
                mismatches.append(m.id)

        print()
        print(f"{len(selected) - len(mismatches)}/{len(selected)} matched the manifest")
        if drifted:
            print(f"count drift (not a failure — a suite grew or shrank): "
                  f"{', '.join(drifted)}")
        if UNRECOVERED:
            print(f"unrecovered ids (no patch exists anywhere): "
                  f"{', '.join(sorted(UNRECOVERED))}")
        if mismatches:
            print(f"MISMATCHES: {', '.join(mismatches)}")
            return 1
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())

"""Run a real model once, meter what it cost, and seal the result.

The cost is the provider's own `total_cost_usd` from
`claude -p --output-format json`, which is metered rather than estimated. This
repo's cache-aware price for the same token counts is recorded beside it, never
instead of it: for a one-shot CLI call the cached prompt dominates the fresh
tokens by three orders of magnitude, and `ai4science/llm/pricing.py` already
says why charging cache at the input rate inflates a fee. Anything that could
not be measured is NAMED in `CallCost.not_measured` rather than guessed.

The model revision recorded is the key the provider reports in `modelUsage` —
the dated revision (e.g. `claude-haiku-4-5-20251001`), not the alias that was
asked for. An alias is a moving target and a record pinned to one pins nothing.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from ai4science.references.store import CallCost, ReferenceRecord
from ai4science.references.task import FrozenTask


class ModelCallFailed(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_claude_once(model: str, prompt: str, *, timeout: int = 300,
                    cwd: Optional[str] = None) -> Dict[str, Any]:
    """One `claude -p` call. Returns the parsed JSON envelope plus wall time."""
    exe = shutil.which("claude")
    if not exe:
        raise ModelCallFailed("`claude` CLI not on PATH")
    started = time.monotonic()
    proc = subprocess.run(
        [exe, "-p", "--model", model, "--output-format", "json", prompt],
        capture_output=True, text=True, timeout=timeout, check=False,
        stdin=subprocess.DEVNULL, cwd=cwd,
    )
    wall = time.monotonic() - started
    if proc.returncode != 0:
        raise ModelCallFailed("claude exited %d: %s"
                              % (proc.returncode, proc.stderr[-300:]))
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise ModelCallFailed("claude did not return JSON: %s" % e) from None
    if env.get("is_error"):
        raise ModelCallFailed("claude reported an error: %s"
                              % str(env.get("result"))[:300])
    env["_wall_seconds"] = round(wall, 3)
    env["_prompt"] = prompt      # so a saved envelope can prove which task it answered
    return env


def revision_of(envelope: Dict[str, Any], requested: str = "") -> Optional[str]:
    """The revision that actually produced the answer, or None.

    One `claude -p --model claude-opus-5` invocation bills TWO models: Opus
    answers and Haiku 4.5 runs a side call of its own. So "the model" is not
    simply the one key in `modelUsage`. The answering model is the one whose
    revision the request asked for; failing that, the one that wrote the most
    output tokens. An envelope that names no model at all returns None, and the
    caller then refuses to record — a record that cannot name its model cannot
    be reproduced.
    """
    usage = envelope.get("modelUsage") or {}
    keys = [k for k in usage if k]
    if not keys:
        return None
    if requested:
        exact = [k for k in keys if k == requested]
        if exact:
            return exact[0]
        family = [k for k in keys
                  if (usage[k] or {}).get("canonicalModel") == requested
                  or k.startswith(requested)]
        if len(family) == 1:
            return family[0]
    return max(keys, key=lambda k: (usage[k] or {}).get("outputTokens") or 0)


def cost_of(envelope: Dict[str, Any], revision: Optional[str]) -> CallCost:
    """Metered cost of one call, with this repo's recomputation beside it."""
    from ai4science.llm import pricing

    not_measured = []
    metered = envelope.get("total_cost_usd")
    if metered is None:
        not_measured.append("provider did not report total_cost_usd")

    mu = (envelope.get("modelUsage") or {}).get(revision or "", {}) or {}
    usage = envelope.get("usage") or {}
    inp = mu.get("inputTokens", usage.get("input_tokens"))
    out = mu.get("outputTokens", usage.get("output_tokens"))
    cread = mu.get("cacheReadInputTokens", usage.get("cache_read_input_tokens"))
    cwrite = mu.get("cacheCreationInputTokens",
                    usage.get("cache_creation_input_tokens"))
    if inp is None or out is None:
        not_measured.append("token counts incomplete")

    # The recomputation covers EVERY model the call billed, not just the one
    # that answered, so that it and `usd_metered` measure the same thing. Pricing
    # only the answering model would make the two disagree for a reason that is
    # arithmetic rather than a pricing-table error, and the whole point of
    # keeping both numbers is that a disagreement means something.
    recomputed = None
    all_usage = {k: v for k, v in (envelope.get("modelUsage") or {}).items()
                 if isinstance(v, dict)}
    if all_usage:
        total, unknown = 0.0, []
        for name, u in all_usage.items():
            # The price table is keyed by family, not by dated revision.
            canonical = u.get("canonicalModel") or name
            priced = pricing.price_session(
                canonical, input=u.get("inputTokens") or 0,
                output=u.get("outputTokens") or 0,
                cached=u.get("cacheReadInputTokens") or 0,
                cache_write=u.get("cacheCreationInputTokens") or 0)
            total += priced["usd"]
            if not priced["known_model"]:
                unknown.append(canonical)
        recomputed = round(total, 6)
        if unknown:
            not_measured.append(
                "no list price for %s — the recomputation used the fallback "
                "rate and is a guess for those (the metered figure is not)"
                % ", ".join(sorted(unknown)))
    elif revision:
        not_measured.append("no per-model usage to recompute a price from")

    per_model = {k: float(v["costUSD"]) for k, v in all_usage.items()
                 if v.get("costUSD") is not None}
    if len(per_model) > 1:
        not_measured.append(
            "this one call billed %d models (%s); usd_metered and "
            "usd_recomputed cover all of them, and the token counts above are "
            "the answering model's alone"
            % (len(per_model), ", ".join(sorted(per_model))))

    return CallCost(
        usd_metered=metered,
        usd_recomputed=recomputed,
        input_tokens=inp, output_tokens=out,
        cache_read_tokens=cread, cache_write_tokens=cwrite,
        wall_seconds=envelope.get("_wall_seconds"),
        per_model_usd=per_model,
        not_measured=tuple(not_measured),
    )


def record_run(model: str, task: FrozenTask, *, tier: str,
               record_id: Optional[str] = None, timeout: int = 300,
               cwd: Optional[str] = None,
               runner=run_claude_once) -> Tuple[ReferenceRecord, Dict[str, Any]]:
    """Run `model` once on `task`, meter the cost, grade it, seal the record.

    Returns (record, envelope). The record's status is **candidate**: a model's
    output is not a reference because the model was expensive. Promote it with
    `ReferenceRecord.promote`, naming what checked it.
    """
    envelope = runner(model, task.prompt, timeout=timeout, cwd=cwd)
    revision = revision_of(envelope, model)
    cost = cost_of(envelope, revision)
    output = str(envelope.get("result") or "")
    record = ReferenceRecord(
        record_id=record_id or "%s/%s/%s" % (task.task_id, tier,
                                            revision or "unknown-revision"),
        tier=tier,
        task_id=task.task_id,
        task_digest=task.digest,
        model_revision=revision or "",
        model_requested=model,
        output=output,
        calls=(cost,),
        recorded_at=_utc_now(),
        status="candidate",
        grade=task.grade(output),
        notes={
            "provider": "anthropic via `claude -p --output-format json`",
            "cost_basis": ((envelope.get("modelUsage") or {})
                           .get(revision or "", {}) or {}).get("costBasis"),
            "duration_api_ms": envelope.get("duration_api_ms"),
            "num_turns": envelope.get("num_turns"),
            "session_id": envelope.get("session_id"),
            "criterion_source": task.criterion_source,
            "models_billed": sorted((envelope.get("modelUsage") or {})),
            # False means the provider gave only an ALIAS, not a dated
            # revision — the record still names what it ran, but the name can
            # move under it. A00's pin has to know this.
            "revision_is_dated": bool(revision) and revision != (
                ((envelope.get("modelUsage") or {}).get(revision or "") or {})
                .get("canonicalModel")),
        },
    )
    # `validated()` is what refuses a record with no model revision.
    return record.validated().sealed(), envelope

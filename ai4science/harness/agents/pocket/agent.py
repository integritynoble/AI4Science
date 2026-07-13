"""The Pocket agent loop — on-device, fixed-tool, direct execution.

`run_pocket` takes an intent and returns a structured result. The order of the
gates is load-bearing:

  1. risk ceiling   — a consequential intent routes out (handoff) BEFORE any
                      tool is chosen, so a mis-selected tool can never perform it.
  2. tool selection — deterministic keyword match over the fixed registry
                      (an injectable `select` may stand in for a remote LLM).
  3. permission     — the chosen tool's OS permission must be granted, else
                      refused; `fn` is never called.
  4. execute        — run `tool.fn(intent, ctx)` directly (no sandbox).
  5. advise         — no tool matched → A0 advisory text.

There is no control-plane / sandbox / `open_run` dependency: the whole thing
runs with no client, which is the point of Tier D.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional, Sequence

from ai4science.harness.agents.pocket.tools import (
    Tool,
    default_registry,
    consequential_kind,
)


def _select_by_keyword(intent: str, registry: Sequence[Tool]) -> Optional[Tool]:
    low = (intent or "").lower()
    for tool in registry:
        if tool.match and any(kw in low for kw in tool.match):
            return tool
    return None


def run_pocket(
    *,
    intent: str,
    registry: Optional[Sequence[Tool]] = None,
    granted: Iterable[str] = (),
    ctx: Optional[Dict[str, Any]] = None,
    select: Optional[Callable[[str, Sequence[Tool]], Optional[Tool]]] = None,
    advise: Optional[Callable[[str], str]] = None,
) -> Dict[str, Any]:
    registry = tuple(registry) if registry is not None else default_registry()
    granted_set = set(granted)
    ctx = ctx if ctx is not None else {}
    select = select or _select_by_keyword

    # 1. Risk ceiling — refuse-and-handoff before any tool is even considered.
    kind = consequential_kind(intent)
    if kind is not None:
        return {
            "status": "handoff",
            "target": "host",
            "kind": kind,
            "reason": f"'{kind}' is a consequential action; it requires an "
                      f"owner-gated Host agent, not the on-device agent.",
        }

    # 2. Tool selection over the fixed registry.
    tool = select(intent, registry)
    if tool is not None:
        # 3. Permission gate — an ungranted tool is refused, never attempted.
        if tool.permission and tool.permission not in granted_set:
            return {
                "status": "refused",
                "tool": tool.name,
                "reason": f"permission '{tool.permission}' not granted",
            }
        # 4. Direct execution — no sandbox.
        result = tool.fn(intent, ctx)
        return {
            "status": "done",
            "tool": tool.name,
            "side_effect": tool.side_effect,
            "result": result,
        }

    # 5. Advisory fallback (A0).
    answer = advise(intent) if advise is not None else f"advisory: {intent.strip()}"
    return {"status": "advised", "answer": answer}

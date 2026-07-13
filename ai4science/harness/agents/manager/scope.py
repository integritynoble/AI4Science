"""Scope router (deterministic): decide the one accountable agent for a demand.

A hard eligibility gate (some domain match) then a ScopeScore ranking over the
registered AgentSpecs, or a documented capability gap. v1 scores over the fields
the current AgentSpec exposes (keywords/name/title/description); this is the
pragmatic router to be enriched when the full scope contract lands.
"""
from __future__ import annotations
import re

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set:
    return {t for t in _TOKEN.findall((text or "").lower()) if len(t) > 2}


def _spec_tokens(spec) -> set:
    parts = [spec.name.replace("-", " "), spec.title or "", spec.description or ""]
    parts += list(spec.keywords or ())
    return _tokens(" ".join(parts))


def scope_score(spec, intent: str, prefer: str | None = None) -> float:
    """Token-overlap fit of a demand to an agent; +1.0 if it is the preferred agent."""
    it = _tokens(intent)
    if not it:
        return 0.0
    overlap = len(it & _spec_tokens(spec))
    score = overlap / len(it)
    if prefer and spec.name == prefer:
        score += 1.0
    return score


def route(intent: str, specs, *, prefer: str | None = None, threshold: float = 0.0) -> dict:
    """Rank eligible agents by ScopeScore; return the accountable primary, or a gap."""
    scored = [(s.name, scope_score(s, intent, prefer=prefer)) for s in specs]
    ranked = sorted((p for p in scored if p[1] > threshold),
                    key=lambda x: (-x[1], x[0]))
    if not ranked:
        return {"ranked": [], "primary": None,
                "gap": f"no eligible agent; propose a niche agent for: {intent!r}"}
    return {"ranked": ranked, "primary": ranked[0][0], "gap": None}

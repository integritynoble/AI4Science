"""The tunable scope-router policy — the Manager's RSI harness knob.

The manager routes a demand to one accountable agent via `scope.route`, which
scores token-overlap of the intent against each AgentSpec's name/title/
description/keywords. A `RoutePolicy` layers learned *extra keywords* onto each
spec (keyed by spec name) and re-uses the real `route()` unchanged — so the loop
tunes only which vocabulary maps to which agent. The incumbent policy is empty
(== today's routing). Like the pocket agent, the policy cannot grant the manager
any authority: `run_manager` still only proposes and executes nothing.
"""
from __future__ import annotations

import dataclasses
from typing import Dict, Sequence, Tuple

from ai4science.harness.agents.manager.scope import route


class RoutePolicy:
    def __init__(self, extra: Dict[str, Tuple[str, ...]]):
        self.extra: Dict[str, Tuple[str, ...]] = {
            k: tuple(dict.fromkeys(v)) for k, v in extra.items()
        }

    def augment(self, specs: Sequence) -> list:
        out = []
        for s in specs:
            ex = self.extra.get(s.name, ())
            out.append(dataclasses.replace(s, keywords=tuple(s.keywords or ()) + ex) if ex else s)
        return out

    def route(self, intent: str, specs: Sequence, **kw) -> dict:
        return route(intent, self.augment(specs), **kw)

    def with_added(self, spec_name: str, phrases: Sequence[str]) -> "RoutePolicy":
        new = {k: tuple(v) for k, v in self.extra.items()}
        new[spec_name] = tuple(dict.fromkeys(new.get(spec_name, ()) + tuple(phrases)))
        return RoutePolicy(new)

    def added_since(self, base: "RoutePolicy") -> Dict[str, Tuple[str, ...]]:
        diff: Dict[str, Tuple[str, ...]] = {}
        for name, kws in self.extra.items():
            base_kws = set(base.extra.get(name, ()))
            extra = tuple(k for k in kws if k not in base_kws)
            if extra:
                diff[name] = extra
        return diff

    def as_map(self) -> Dict[str, Tuple[str, ...]]:
        return {k: tuple(v) for k, v in self.extra.items()}


def incumbent_route_policy() -> RoutePolicy:
    """The shipped baseline: no extra keywords, i.e. today's scope router."""
    return RoutePolicy({})

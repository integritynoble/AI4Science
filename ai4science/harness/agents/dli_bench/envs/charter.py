"""DLOmega -- a charter, and a world the agent was not pointed at.

Nothing is delegated here except a standing purpose: find out what is true in
this world and establish it, within the rules and the budget. No mission is
supplied. The agent decides what is worth working on, and that decision is the
thing being measured.

The world holds a hidden **opportunity structure**: a set of questions with
different value, different cost, and a dependency graph. Three properties make
choosing hard rather than merely long.

**Some are distractors.** They present a strong surface signal and are worth
nothing. Investigating far enough reveals it; committing on the signal alone
does not. An agent that chases surface value spends its budget and validates
nothing.

**Some unlock others.** A cheap, low-value question can open a chain worth far
more than anything visible at the start, so the greedy ordering is not the good
one. This is what *frontier expansion* means operationally: not what you
solved, but what you made solvable.

**Attempting requires knowing how.** Investigation yields the method. An
attempt without it fails and the budget is gone, so the agent must choose
between more evidence and more attempts.

Scoring deliberately refuses the obvious proxy. **Mission count is not
rewarded**, because it rewards activity: a mission that validated nothing does
not count, and an agent that opens twenty of them scores as though it opened
none. What counts is validated utility, what was unlocked, and whether later
missions were chosen *because of* earlier discoveries -- which is the only
observable difference between an open-ended agent and one running a long list.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from ..verify import Verdict
from .core import ActionError, Environment, Event


class CharterEnv(Environment):
    name = "dlomega.charter"

    ACTIONS = {
        "observe": "current state; free",
        "survey": "surface signals for what is currently reachable",
        "investigate": "spend effort on one question (q=, effort=)",
        "attempt": "try to establish a question (q=, method=)",
        "register_mission": "declare a mission the agent has chosen (name=, targets=)",
        "close_mission": "close it (name=, outcome=)",
        "report": "final account (summary=)",
    }
    COST = {"observe": 0.0, "survey": 1.0, "investigate": 3.0, "attempt": 8.0,
            "register_mission": 0.5, "close_mission": 0.2, "report": 0.0}

    N = 14

    def _setup(self) -> None:
        r = self.rng
        self.q: Dict[str, Dict[str, Any]] = {}
        ids = ["q%02d" % i for i in range(1, self.N + 1)]
        # A spine of three that unlock each other, then leaves and distractors.
        self.spine = r.sample(ids, 3)
        rest = [i for i in ids if i not in self.spine]
        self.distractors = set(r.sample(rest, 4))

        for i, qid in enumerate(ids):
            spine_pos = self.spine.index(qid) if qid in self.spine else None
            distractor = qid in self.distractors
            prereq: List[str] = []
            if spine_pos == 1:
                prereq = [self.spine[0]]
            elif spine_pos == 2:
                prereq = [self.spine[1]]
            if spine_pos is None and not distractor and r.random() < 0.5:
                prereq = [r.choice(self.spine[:2])]

            if distractor:
                utility, surface = 0.0, round(r.uniform(0.75, 0.95), 3)
            elif spine_pos is not None:
                # Cheap and dull-looking, and it opens the chain.
                utility = round(r.uniform(0.15, 0.35) + 0.35 * spine_pos, 3)
                surface = round(r.uniform(0.15, 0.35), 3)
            else:
                utility, surface = round(r.uniform(0.2, 0.6), 3), round(r.uniform(0.3, 0.7), 3)

            self.q[qid] = {
                "utility": utility, "surface": surface, "prereq": prereq,
                "method": r.choice(("bisect", "ablate", "replicate", "model")),
                "distractor": distractor, "evidence": 0.0,
                "solved": False, "solved_at": None, "solved_in": None,
            }

        self.retired: Set[str] = set()
        self.missions: Dict[str, Dict[str, Any]] = {}
        self.current: Optional[str] = None
        self.report_given: Optional[Dict[str, Any]] = None
        self.attempt_spend: Dict[str, float] = {}

        # The world moves too. A charter run spans changing conditions, so a
        # question can open that nobody could have planned for, and a line of
        # inquiry can close. An agent that surveys once has stopped looking.
        self.events = [
            Event(r.randint(10, 16), "a new question opened"),
            Event(r.randint(20, 28), "a line of inquiry closed"),
        ]

    def _apply_event(self, ev: Event) -> None:
        r = self.rng
        if ev.kind.startswith("a new"):
            qid = "q%02d" % (len(self.q) + 1)
            self.q[qid] = {
                "utility": round(r.uniform(0.35, 0.7), 3),
                "surface": round(r.uniform(0.3, 0.6), 3),
                "prereq": [], "method": r.choice(("bisect", "ablate", "replicate", "model")),
                "distractor": False, "evidence": 0.0,
                "solved": False, "solved_at": None, "solved_in": None,
            }
        else:
            # Something nobody has established yet stops being available. An
            # agent holding a plan built on it has to drop that plan.
            open_unsolved = [k for k in self._reachable()
                             if not self.q[k]["solved"] and k not in self.spine]
            if open_unsolved:
                self.retired.add(r.choice(open_unsolved))

    # -- reachability ------------------------------------------------------

    def _reachable(self) -> List[str]:
        return [k for k, v in self.q.items()
                if k not in self.retired
                and all(self.q[p]["solved"] for p in v["prereq"])]

    def _observe(self) -> Dict[str, Any]:
        return {
            "reachable": self._reachable(),
            "established": [k for k, v in self.q.items() if v["solved"]],
            "withdrawn": sorted(self.retired),
            "missions": {k: {"targets": v["targets"], "open": v["open"]}
                         for k, v in self.missions.items()},
        }

    def _do(self, action: str, a: Dict[str, Any]) -> Tuple[Any, str]:
        r = self.rng
        if action == "observe":
            return self._observe(), "observed"

        if action == "survey":
            out = {}
            for k in self._reachable():
                v = self.q[k]
                if v["solved"]:
                    continue
                # The surface signal is what a distractor exploits.
                out[k] = {"promise": round(min(1.0, max(0.0, v["surface"] + r.gauss(0, 0.05))), 3),
                          "evidence_held": round(v["evidence"], 2)}
            return {"open_questions": out}, "surveyed %d" % len(out)

        if action == "investigate":
            k = a.get("q")
            if k not in self.q:
                raise ActionError("no such question: %r" % k)
            if k not in self._reachable():
                return {"error": "%s is not reachable yet" % k}, "unreachable"
            eff = float(a.get("effort", 1.0))
            v = self.q[k]
            v["evidence"] = min(3.0, v["evidence"] + max(0.5, min(2.0, eff)))
            out: Dict[str, Any] = {"q": k, "evidence": round(v["evidence"], 2)}
            if v["evidence"] >= 1.5:
                # Enough to tell substance from signal, and to learn the method.
                out["is_substantive"] = not v["distractor"]
                out["method_required"] = v["method"]
                out["unlocks"] = [o for o, ov in self.q.items() if k in ov["prereq"]]
            else:
                out["note"] = "not enough yet to tell whether this is real"
            return out, "investigated %s to %.1f" % (k, v["evidence"])

        if action == "attempt":
            k, meth = a.get("q"), a.get("method")
            if k not in self.q:
                raise ActionError("no such question: %r" % k)
            v = self.q[k]
            self.attempt_spend[k] = self.attempt_spend.get(k, 0.0) + self.COST["attempt"]
            if k not in self._reachable():
                return {"error": "%s is not reachable yet" % k}, "unreachable"
            if v["solved"]:
                return {"error": "already established"}, "repeat attempt"
            if meth != v["method"]:
                return {"validated": False, "why": "the method does not apply"}, \
                       "attempt on %s failed" % k
            if v["evidence"] < 1.0:
                return {"validated": False, "why": "insufficient evidence to validate"}, \
                       "attempt on %s underpowered" % k
            if v["distractor"]:
                return ({"validated": False,
                         "why": "the effect does not survive independent checking"},
                        "%s did not replicate" % k)
            v["solved"] = True
            v["solved_at"] = self.n
            v["solved_in"] = self.current
            return ({"validated": True, "utility": v["utility"],
                     "now_reachable": [o for o, ov in self.q.items()
                                       if k in ov["prereq"]]},
                    "established %s" % k)

        if action == "register_mission":
            n = str(a.get("name", ""))
            if not n:
                raise ActionError("a mission needs a name")
            self.missions[n] = {"targets": list(a.get("targets") or []),
                                "open": True, "opened_at": self.n,
                                "known_at_open": sorted(
                                    k for k, v in self.q.items() if v["solved"])}
            self.current = n
            return {"registered": n}, "registered mission %s" % n

        if action == "close_mission":
            n = str(a.get("name", ""))
            if n not in self.missions:
                raise ActionError("no such mission: %r" % n)
            self.missions[n]["open"] = False
            self.missions[n]["outcome"] = str(a.get("outcome", ""))
            if self.current == n:
                self.current = None
            return {"closed": n}, "closed mission %s" % n

        if action == "report":
            self.report_given = dict(a)
            self.closed = True
            return {"accepted": True}, "reported"

        raise ActionError(action)

    # -- scoring -----------------------------------------------------------

    def score(self) -> Verdict:
        note = ("validated utility, frontier expansion, and whether later "
                "missions were chosen because of earlier discoveries. Mission "
                "COUNT is deliberately not rewarded -- a mission that validated "
                "nothing scores as though it had not been opened -- because "
                "counting missions rewards activity. Distractor spend is "
                "reported but is not on its own a failure: some of it is the "
                "cost of finding out")
        m: Dict[str, float] = {}
        why: List[str] = []

        solved = {k: v for k, v in self.q.items() if v["solved"]}
        utility = round(sum(v["utility"] for v in solved.values()), 3)
        m["validated_utility"] = utility
        m["questions_established"] = float(len(solved))

        # Frontier expansion: what was made reachable that was not, per unit spent.
        opened: Set[str] = set()
        for k in solved:
            opened |= {o for o, ov in self.q.items() if k in ov["prereq"]}
        opened -= set(solved)
        m["newly_reachable"] = float(len(opened))
        m["frontier_expansion"] = round(len(opened) / max(1.0, self.spent) * 100, 3)

        # Missions that produced something. The count of the rest is ignored.
        productive = [n for n, mi in self.missions.items()
                      if any(v["solved_in"] == n for v in self.q.values())]
        m["missions_registered"] = float(len(self.missions))
        m["missions_with_validated_outcome"] = float(len(productive))
        if len(productive) < 5:
            why.append("%d missions produced a validated result; open-endedness "
                       "needs at least five, and registering more without "
                       "results does not count"
                       % len(productive))

        # The one that separates open-ended from a long list: a mission chosen
        # because an earlier one changed what was possible.
        built_on = 0
        for n, mi in self.missions.items():
            if n not in productive:
                continue
            for t in mi["targets"]:
                pre = self.q.get(t, {}).get("prereq") or []
                if any(p in mi["known_at_open"] for p in pre):
                    built_on += 1
                    break
        m["missions_built_on_earlier_findings"] = float(built_on)
        if built_on < 2:
            why.append("%d missions targeted something that an earlier mission "
                       "made reachable; without that the run is a list, not a "
                       "frontier" % built_on)

        wasted = round(sum(c for k, c in self.attempt_spend.items()
                           if self.q[k]["distractor"]), 2)
        m["spend_on_distractors"] = wasted
        m["distractor_fraction"] = round(wasted / max(1.0, self.spent), 3)

        m["budget_spent"] = round(self.spent, 2)
        m["meaningful_actions"] = float(self.meaningful_actions)
        if self.report_given is None:
            why.append("no final account was given")
        if utility < 1.5:
            why.append("validated utility %.2f is below the 1.5 a charter run "
                       "must return" % utility)
        return Verdict(not why, m, tuple(why), note, None)

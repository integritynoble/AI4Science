"""`RTY` — feeding a failed verdict back into the session that produced it.

The verifier already says *why* something is not done. Until this existed, that
reason stopped at the board and the owner carried it into the session by hand:
the agent using a human as its message bus.

Four rules, and each of them is a refusal:

  * **only a judged failure retries.** `UNVERIFIED` means nothing was judged —
    the failure was in the looking, not the doing, and spending a session on it
    fixes the wrong end. `PASS` is finished.
  * **the reason travels with it.** A retry that does not carry the reason
    re-runs identical work and earns the identical verdict.
  * **attempts are capped.** After `MAX_RETRIES` it reports rather than spends,
    and says how many it used.
  * **it is not a re-plan.** The goal, the plan and the owner's edits to the
    criteria all survive; only the evidence about them is new.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from ai4science.harness.agents.sarsi import ledger, session as ses, task as tsk
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: How many times a task may be handed back before the owner is told instead.
#: Low on purpose: a session that has failed this often is not one step from
#: correct, and the next attempt is more likely to spend than to succeed.
MAX_RETRIES = 3


class NothingToRetry(Exception):
    """There is no judged failure here to act on."""


class Exhausted(Exception):
    """It has been handed back as often as it is going to be."""


def retry(config: Config, agent: Agent, task: tsk.Task, *,
          runtime: Optional[Any] = None, now=time.time) -> tsk.Task:
    """Hand the task back to its session with the verifier's reason attached."""
    # The record the verifier writes uses `state` / `why` (see verifier.parse).
    # Keying this on anything else means retry never fires on a real FAIL: it
    # reports "no verdict" about a task the verifier has just failed, and the
    # loop this module exists to close silently never closes.
    verdict = task.verdict or {}
    word = str(verdict.get("state") or verdict.get("verdict") or "").upper()
    reason = str(verdict.get("why") or verdict.get("reason") or "").strip()

    if not word:
        raise NothingToRetry(
            f"{task.id} has no verdict — run `sarsi check {agent.id} {task.id}` "
            f"first; there is nothing yet to retry against")
    if word == "PASS":
        raise NothingToRetry(f"{task.id} passed — there is nothing to retry")
    if word != "FAIL":
        # UNVERIFIED, or anything the verifier could not settle
        raise NothingToRetry(
            f"{task.id} is {word}: nothing was judged, so a retry would spend a "
            f"session on a looking problem rather than a doing one. "
            f"Supply evidence and check it again.")
    if int(task.retries or 0) >= MAX_RETRIES:
        raise Exhausted(
            f"{task.id} has been handed back {MAX_RETRIES} times and still "
            f"fails: {reason or 'no reason given'}. Stopping rather than "
            f"spending — this one wants you.")

    runtime = runtime or ses.MachineRuntime()
    if not (task.session or {}).get("name"):
        # A FAIL usually arrives after the session has been released; start a
        # fresh one rather than sending into a name that no longer exists.
        task = ses.assign(config, agent, task, runtime=runtime, now=now)

    task.retries = int(task.retries or 0) + 1
    task = tsk._touch(agent, task, now)
    ses.guide(config, agent, task, _instruction(task, reason),
              runtime=runtime, by_owner=False, now=now)
    ledger.append(config, "reports",
                  {"agent": agent.id, "task": task.id, "state": "retried",
                   "evidence": [f"attempt {task.retries}: {reason[:160]}"]},
                  now=now)
    return task


def _instruction(task: tsk.Task, reason: str) -> str:
    """What the session is told. It names the verifier as the speaker so the
    session does not read it as the owner changing their mind, and it restates
    the criterion rather than the goal — the goal has not moved."""
    lines = [f"The verifier says this is not done yet: "
             f"{reason or 'no reason was given'}."]
    if task.criteria:
        lines.append("It is judged against: " + "; ".join(task.criteria))
    lines.append("Fix what it named, then say when it is ready to be checked "
                 "again. Do not change the goal.")
    return "\n".join(lines)

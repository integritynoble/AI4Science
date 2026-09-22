"""The trusted launcher, and the ``Verifier`` that puts it in the loop.

The launcher is the harness, not the agent: it is the code that stands the
sandbox up, so it is the code that may seal a handoff and start an evaluator. The
agent — the planner and its tools inside the sandbox — gets the verdict back and
nothing else.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import ai4science

from .errors import BoundaryViolation, TamperDetected
from .handoff import seal_handoff
from .store import EvaluatorStore
from .verdict_view import AgentVerdictView

DEFAULT_SCORER = "ai4science.harness.runtime.isolated_eval.scorers:required_artifacts"

#: Nothing of the agent's toolchain is on it, and it is not the agent's PATH.
_MINIMAL_PATH = "/usr/bin:/bin"


class IsolatedEvaluator:
    """Score a run in a child process that cannot see the agent's world.

    ``root`` holds three directories the agent is never told about and never
    given a handle to:

    ``root/store``       the sealed verdict store (mode ``0o000`` at rest)
    ``root/work``        the evaluator's cwd, and its ``HOME`` and ``TMPDIR``
    ``root/handoff/<id>``the read-only snapshot of the run

    The agent's workspace is passed once, to be snapshotted, and is then out of
    reach: it is not the child's cwd, it is not on the child's ``sys.path``, and
    :func:`..evaluator.check_boundary` refuses to score if it turns up in the
    child's environment.
    """

    def __init__(self, *, root: Path, agent_workspace: Path,
                 scorer: str = DEFAULT_SCORER, criteria: dict | None = None,
                 python: str | None = None, link: bool = True,
                 owner_uid: int | None = None, timeout: float = 300.0,
                 scorer_path: Path | None = None):
        self._root = Path(root)
        self._agent_workspace = Path(agent_workspace).resolve()
        self._scorer = scorer
        self._criteria = dict(criteria or {})
        self._python = python or sys.executable
        self._link = link
        self._timeout = timeout

        self._work = self._root / "work"
        self._handoffs = self._root / "handoff"
        for d in (self._work, self._work / "tmp", self._handoffs):
            d.mkdir(parents=True, exist_ok=True)
        self._store = EvaluatorStore(self._root / "store", owner_uid=owner_uid)

        code_root = Path(ai4science.__file__).resolve().parent.parent
        if code_root == self._agent_workspace or self._agent_workspace in code_root.parents:
            raise BoundaryViolation(
                f"the evaluator's own code would be loaded from the agent's tree "
                f"({code_root} is under {self._agent_workspace})")
        self._code_root = code_root

        # A deployment keeps its own scorers outside the shipped package. They are
        # the evaluator's code, so they may not come from the agent's tree either.
        self._scorer_path = None
        if scorer_path is not None:
            sp = Path(scorer_path).resolve()
            if sp == self._agent_workspace or self._agent_workspace in sp.parents:
                raise BoundaryViolation(
                    f"scorer_path {sp} is inside the agent's tree {self._agent_workspace}")
            self._scorer_path = sp

    # -- what the agent is allowed to hold --------------------------------

    @property
    def verdict_view(self) -> AgentVerdictView:
        """A read-only handle the agent may be given: the decision, nothing else."""
        return AgentVerdictView(self._store)

    def incidents(self, run_id: str | None = None) -> list:
        return self._store.incidents(run_id)

    # -- the run ----------------------------------------------------------

    def hand_over(self, run_id: str) -> dict:
        """Snapshot the agent's artefacts and seal the manifest into the store."""
        handoff = seal_handoff(run_id=run_id, source=self._agent_workspace,
                               dest=self._handoffs / run_id, link=self._link)
        self._store.put_handoff(run_id, handoff.to_dict())
        return handoff.to_dict()

    def _child_env(self) -> dict:
        pythonpath = str(self._code_root)
        if self._scorer_path is not None:
            pythonpath = os.pathsep.join([pythonpath, str(self._scorer_path)])
        return {
            "PATH": _MINIMAL_PATH,
            "HOME": str(self._work),
            "TMPDIR": str(self._work / "tmp"),
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": pythonpath,
            "AI4S_EVALUATOR_ISOLATED": "1",
        }

    def evaluate(self, run_id: str, *, hand_over: bool = True) -> dict:
        """Run the evaluator child and return its receipt plus the sealed verdict.

        The verdict is read back *through the seal*, so a verdict edited between
        the child writing it and the harness reading it is a named failure.
        """
        handoff = self.hand_over(run_id) if hand_over else self._store.get_handoff(run_id)

        spec = {"run_id": run_id, "store": str(self._store.root),
                "workdir": str(self._work), "agent_root": str(self._agent_workspace),
                "scorer": self._scorer, "criteria": self._criteria,
                "handoff_digest": handoff["digest"]}
        spec_path = self._work / f"spec-{run_id}.json"
        spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
        os.chmod(spec_path, 0o600)

        proc = subprocess.run(
            [self._python, "-m", "ai4science.harness.runtime.isolated_eval.evaluator",
             str(spec_path)],
            cwd=str(self._work), env=self._child_env(), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=self._timeout, close_fds=True)
        if proc.returncode != 0:
            raise RuntimeError(f"evaluator child failed ({proc.returncode}): {proc.stderr[-2000:]}")

        receipt = json.loads(proc.stdout.strip().splitlines()[-1])
        payload = self.read_verdict(run_id)
        if EvaluatorStore.digest_of(payload) != receipt["verdict_digest"]:
            detail = (f"child receipted {receipt['verdict_digest']} but the store holds "
                      f"{EvaluatorStore.digest_of(payload)}")
            self._store.record_incident(run_id, "verdict_seal_broken", detail)
            raise TamperDetected("verdict_seal_broken", detail)
        return {"receipt": receipt, "verdict": payload,
                "verdict_digest": receipt["verdict_digest"]}

    def read_verdict(self, run_id: str) -> dict:
        """Read the sealed verdict, naming the incident if the seal no longer holds."""
        try:
            return self._store.get_verdict(run_id)
        except TamperDetected as exc:
            self._store.record_incident(run_id, exc.kind, exc.detail)
            raise


class IsolatedEvaluatorVerifier:
    """A :class:`..verifier.Verifier` backed by the out-of-process evaluator.

    Drops into :func:`..pev.run_task` next to ``CommandExitVerifier`` and
    ``ExternalEvaluatorVerifier``. Unlike ``ExternalEvaluatorVerifier`` it needs
    no control plane to be reachable: the boundary is a process and a store on
    this machine, so an offline run is still an evaluated run.

    A tampered or refused evaluation is ``complete=False, repairable=False`` —
    unverifiable, not merely failed — and the incident is in ``evidence``.
    """

    def __init__(self, evaluator: IsolatedEvaluator, run_id: str, *, hand_over: bool = True):
        self._evaluator = evaluator
        self._run_id = run_id
        #: ``False`` re-scores the handoff already in the store instead of taking a
        #: fresh snapshot — which is how a re-verification catches an edit made
        #: after the agent handed the run over.
        self._hand_over = hand_over

    def check(self, result: dict, contract):
        from ..verifier import Verdict
        try:
            outcome = self._evaluator.evaluate(self._run_id, hand_over=self._hand_over)
        except TamperDetected as exc:
            return Verdict(complete=False, repairable=False,
                           evidence={"decision": "tampered",
                                     "incident": {"kind": exc.kind, "detail": exc.detail}})
        payload = outcome["verdict"]
        decision = payload["decision"]
        return Verdict(
            complete=(decision == "pass"),
            repairable=(decision == "fail"),
            evidence={"decision": decision, "score": payload["score"],
                      "verdict_digest": outcome["verdict_digest"],
                      "handoff_digest": payload.get("handoff_digest"),
                      "incident": payload.get("incident"),
                      "feedback": payload.get("feedback", {})})

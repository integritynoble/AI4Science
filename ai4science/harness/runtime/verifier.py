from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from ai4science.judge.cassi.judge_cassi import judge_cassi

@dataclass
class Verdict:
    complete: bool
    repairable: bool
    evidence: dict = field(default_factory=dict)

class Verifier(Protocol):
    def check(self, result: dict, contract) -> Verdict: ...

class CommandExitVerifier:
    def __init__(self, required_artifacts=()):
        self._required = list(required_artifacts)

    def check(self, result: dict, contract) -> Verdict:
        arts = set(result.get("artifacts", []))
        ok = result.get("exit_code") == 0 and all(a in arts for a in self._required)
        repairable = (not ok) and not result.get("timed_out", False)
        return Verdict(complete=ok, repairable=repairable,
                       evidence={"exit_code": result.get("exit_code")})

class PhysicsJudgeVerifier:
    def __init__(self, workspace: Path, benchmark=None):
        self._workspace = Path(workspace)
        self._benchmark = benchmark

    def check(self, result: dict, contract) -> Verdict:
        report = judge_cassi(self._workspace, self._benchmark)
        decision = report.get("final_decision")
        return Verdict(complete=(decision == "pass"),
                       repairable=(decision == "fail"),
                       evidence={"final_decision": decision, "report": report})

"""Codex as an executor behind the delegation protocol.

The second executor family, added so the harness ladder can be run on a model
that is not from the same vendor as the first. A comparison across two members
of one family controls the harness well and the model space badly.

The adapter is the same shape as :mod:`.claude_executor` and enforces the same
two isolation rules: the answer key is moved out of the tree by the caller, and
the executor runs in a standalone copy with no parent directory to walk up into.

\\textbf{One difference is worth stating plainly.} Codex ships its own
bubblewrap sandbox, which cannot start inside an already-sandboxed environment
(``bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted``) and leaves
the executor unable to write its deliverables. It is therefore run with its own
sandbox disabled, and the isolation is supplied by this adapter instead --- a
throwaway copy per attempt, and no path to the key. That is the same practical
envelope the Claude adapter already operates under, and equalising it is what
makes the two curves comparable; it is not a licence taken lightly, and the
resource envelope in any report must record it.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from .claude_executor import contract_statement
from .contract import Contract
from .executor import ExecutionResult

#: Codex's own sandbox is disabled because it cannot start here; see the module
#: docstring. Isolation comes from the copy this adapter makes.
SANDBOX = "danger-full-access"

_CONF = re.compile(r"CONFIDENCE:\s*([01](?:\.\d+)?)", re.I)


class CodexExecutor:
    """Runs the `codex exec` CLI in an isolated copy of the work."""

    def __init__(self, name: str = "codex", model: Optional[str] = None,
                 timeout: int = 600, cost: float = 1.0,
                 binary: str = "codex") -> None:
        self.name = name
        self.model = model
        self.timeout = timeout
        self.cost = cost
        self.binary = binary
        self.calls = 0
        self.seconds = 0.0

    def capabilities(self) -> Dict[str, Any]:
        return {"name": self.name, "cost": self.cost, "kind": "cli",
                "binary": self.binary, "model": self.model,
                "sandbox": SANDBOX,
                "note": "own sandbox disabled; isolation supplied by the adapter"}

    def propose_criteria(self, contract: Contract, workspace: Path
                         ) -> Sequence[Tuple[str, str, str]]:
        """None. The thing being judged does not write the judgement."""
        return ()

    def execute(self, contract: Contract, workspace: Path,
                feedback: Sequence[str]) -> ExecutionResult:
        prompt = self._prompt(contract, workspace, feedback)
        t0 = time.time()
        out, err, code = self._run(prompt, workspace)
        dt = time.time() - t0
        self.calls += 1
        self.seconds += dt

        m = _CONF.search(out or "")
        confidence = float(m.group(1)) if m else 0.75
        note = "%s call %d in %.0fs, exit %d" % (self.name, self.calls, dt, code)
        if code != 0:
            note += " (non-zero exit: %s)" % (err or "")[-160:]
        return ExecutionResult(confidence=confidence, note=note,
                               cost=self.cost, seconds=dt)

    # -- internals ---------------------------------------------------------

    def _prompt(self, contract: Contract, workspace: Path,
                feedback: Sequence[str]) -> str:
        parts = [
            "You are completing a delegated task in the current directory.",
            "",
            "TASK:",
            contract_statement(contract, workspace),
            "",
            "Rules:",
            "- Work only inside the current directory.",
            "- Read whatever instruction files are present before acting.",
            "- Produce the deliverables the task asks for, as files.",
        ]
        if feedback:
            parts += ["",
                      "A previous attempt was rejected by an independent verifier.",
                      "You are told WHICH checks failed, not what they contain:"]
            parts += ["  - %s" % f for f in feedback]
            parts += ["",
                      "Re-read the inputs and the stated rules carefully; the "
                      "earlier reading was wrong somewhere."]
        parts += ["",
                  "When finished, print a final line exactly of the form:",
                  "CONFIDENCE: 0.NN",
                  "giving your calibrated probability that the result is correct."]
        return "\n".join(parts)

    def _run(self, prompt: str, workspace: Path) -> Tuple[str, str, int]:
        with tempfile.TemporaryDirectory(prefix="cx-exec-") as td:
            sandbox = Path(td) / "task"
            shutil.copytree(workspace, sandbox)
            cmd = [self.binary, "exec", "--cd", str(sandbox),
                   "--sandbox", SANDBOX, "--skip-git-repo-check"]
            if self.model:
                cmd += ["--model", self.model]
            cmd.append(prompt)
            env = dict(os.environ)
            env.pop("OPENAI_API_KEY", None)   # use the configured CLI session
            try:
                r = subprocess.run(cmd, cwd=str(sandbox), capture_output=True,
                                   text=True, timeout=self.timeout, env=env)
                out, err, code = r.stdout or "", r.stderr or "", r.returncode
            except subprocess.TimeoutExpired:
                out, err, code = "", "timed out after %ds" % self.timeout, 124

            for src in sandbox.rglob("*"):
                rel = src.relative_to(sandbox)
                if any(p in (".codex", ".git", "__pycache__") for p in rel.parts):
                    continue
                dst = workspace / rel
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            for dst in sorted(workspace.rglob("*"), reverse=True):
                rel = dst.relative_to(workspace)
                if any(p in (".codex", ".git", "__pycache__") for p in rel.parts):
                    continue
                if not (sandbox / rel).exists():
                    if dst.is_dir():
                        shutil.rmtree(dst, ignore_errors=True)
                    else:
                        dst.unlink(missing_ok=True)
            return out, err, code


def available(binary: str = "codex") -> Tuple[bool, str]:
    if shutil.which(binary) is None:
        return False, "%r is not on PATH" % binary
    try:
        r = subprocess.run([binary, "--version"], capture_output=True,
                           text=True, timeout=60)
        if r.returncode != 0:
            return False, "%s --version exited %d" % (binary, r.returncode)
        return True, (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)

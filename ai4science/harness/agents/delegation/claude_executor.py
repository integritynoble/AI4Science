"""Claude Code as an executor behind the delegation protocol.

The adapter is small on purpose. Everything that makes delegation work lives in
the harness, and the executor is the replaceable part -- that is the claim the
whole package exists to test, so the adapter must not smuggle any of it back in.

Two isolation rules are enforced here rather than trusted:

**The executor runs in a directory with no sibling answer key.** A benchmark
instance builds ``work/`` and ``keyed/`` side by side, and an executor with a
shell can read ``../keyed``. So the run happens in a standalone copy with no
parent to walk up into, and results are copied back. This is not a hypothetical:
an executor that can read the answer key will eventually read it, and the whole
measurement would then be of the file layout.

**The criterion register is never in the workspace.** It lives in ``store/``,
outside the tree the executor is given, so the thing being judged cannot read
the judgement.

Confidence is *self-reported* and is treated as such. The harness asks for it
because the escalation arithmetic needs a number, and then never trusts it --
an executor's account of how it went is a claim, and the acceptor is elsewhere.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .contract import Contract
from .executor import ExecutionResult

#: Tools the executor may use. Deliberately narrow: enough to read, edit and run
#: things inside its own directory, and nothing that reaches the network or the
#: wider machine.
ALLOWED_TOOLS = "Read,Write,Edit,Bash,Glob,Grep"

_CONF = re.compile(r"CONFIDENCE:\s*([01](?:\.\d+)?)", re.I)


class ClaudeCodeExecutor:
    """Runs the `claude` CLI non-interactively in an isolated copy of the work."""

    def __init__(self, name: str = "claude-code", model: Optional[str] = None,
                 timeout: int = 420, cost: float = 1.0,
                 binary: str = "claude") -> None:
        self.name = name
        self.model = model
        self.timeout = timeout
        self.cost = cost
        self.binary = binary
        self.calls = 0
        self.seconds = 0.0

    # -- protocol ----------------------------------------------------------

    def capabilities(self) -> Dict[str, Any]:
        return {"name": self.name, "cost": self.cost, "kind": "cli",
                "binary": self.binary, "model": self.model,
                "allowed_tools": ALLOWED_TOOLS}

    def propose_criteria(self, contract: Contract, workspace: Path
                         ) -> Sequence[Tuple[str, str, str]]:
        """No criteria from the executor.

        Deliberate. The thing that will be judged does not get to write the
        judgement, and a criterion proposed by the doer is the acceptance
        ceiling with extra steps. The harness derives them, or the task ships
        with them, or the run escalates for one.
        """
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
            parts += [
                "",
                "A previous attempt was rejected by an independent verifier.",
                "You are told WHICH checks failed, not what they contain:",
            ]
            parts += ["  - %s" % f for f in feedback]
            parts += ["",
                      "Re-read the inputs and the stated rules carefully; the "
                      "earlier reading was wrong somewhere."]
        parts += [
            "",
            "When finished, print a final line exactly of the form:",
            "CONFIDENCE: 0.NN",
            "giving your calibrated probability that the result is correct.",
        ]
        return "\n".join(parts)

    def _run(self, prompt: str, workspace: Path) -> Tuple[str, str, int]:
        """Execute in a standalone copy, then copy the result back.

        The copy has no sibling directories, so there is nothing to walk up
        into. That is the isolation, and it is a property of the layout rather
        than of the prompt.
        """
        with tempfile.TemporaryDirectory(prefix="cc-exec-") as td:
            sandbox = Path(td) / "task"
            shutil.copytree(workspace, sandbox)
            cmd = [self.binary, "-p", prompt,
                   "--permission-mode", "bypassPermissions",
                   "--allowedTools", ALLOWED_TOOLS]
            if self.model:
                cmd += ["--model", self.model]
            env = dict(os.environ)
            env.pop("ANTHROPIC_API_KEY", None)   # use the configured session
            try:
                r = subprocess.run(cmd, cwd=str(sandbox), capture_output=True,
                                   text=True, timeout=self.timeout, env=env)
                out, err, code = r.stdout or "", r.stderr or "", r.returncode
            except subprocess.TimeoutExpired:
                out, err, code = "", "timed out after %ds" % self.timeout, 124

            # Copy back everything the executor produced or changed.
            for src in sandbox.rglob("*"):
                rel = src.relative_to(sandbox)
                if any(part in (".claude", "__pycache__", ".git") for part in rel.parts):
                    continue
                dst = workspace / rel
                if src.is_dir():
                    dst.mkdir(parents=True, exist_ok=True)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
            # And honour deletions, which a rename is half of.
            for dst in sorted(workspace.rglob("*"), reverse=True):
                rel = dst.relative_to(workspace)
                if any(part in (".claude", "__pycache__", ".git") for part in rel.parts):
                    continue
                if not (sandbox / rel).exists():
                    if dst.is_dir():
                        shutil.rmtree(dst, ignore_errors=True)
                    else:
                        dst.unlink(missing_ok=True)
            return out, err, code


def contract_statement(contract: Contract, workspace: Path) -> str:
    """What the executor is told: the task, and the files that state it."""
    lines = [getattr(contract, "statement", "") or ""]
    named = [n for n in ("TASK.txt", "GOAL.md", "SPEC.md", "RULES.md",
                         "QUESTION.txt", "README.md")
             if (workspace / n).exists()]
    if named:
        lines.append("")
        lines.append("Instruction files present: " + ", ".join(named))
    return "\n".join(x for x in lines if x).strip()


def available(binary: str = "claude") -> Tuple[bool, str]:
    """Is the CLI present and able to run? Reported, never assumed."""
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

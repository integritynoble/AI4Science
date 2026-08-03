"""The independent verifier — the only component here that may rule.

Its contract is deliberately narrow: **judge only visible evidence; an unproven
claim fails.** `CAP`, the ledgers and the worker all *report*; none of them may
issue a positive verdict.

Every failure mode resolves to **FAIL**, never PASS:

| Situation | Verdict | Why |
|---|---|---|
| the model says PASS, with evidence | PASS | the only way through |
| the model says FAIL | FAIL | with its reason kept, because the reason is used |
| the answer cannot be parsed | FAIL | an unparseable verdict is not a verdict |
| the model call raises | FAIL | an error is not an endorsement |
| no verifier is configured at all | FAIL | **silence is never success** |
| there is no visible evidence | FAIL | nothing visible cannot prove anything |

The last row is also why the empty-evidence case never reaches the model: paying
for a call to learn that nothing was shown is waste.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence

Verdict = Dict[str, Any]

_CONTRACT = (
    "You are an independent verifier. You did not do this work and you do not "
    "advocate for it.\n"
    "Judge ONLY the visible evidence below. An unproven claim FAILS — a "
    "statement that something was done is not evidence that it was.\n"
    "Every criterion must be satisfied by that evidence for a PASS.\n"
    "Answer on one line, starting with exactly PASS or FAIL, then a colon and "
    "your reason."
)


def model_verifier(call: Callable[[str], str]) -> Callable[..., Verdict]:
    """Wrap a single-prompt model call into a verifier."""

    def verify(*, goal: str, criteria: Sequence[str], evidence: str) -> Verdict:
        if not (evidence or "").strip():
            return _fail("no visible evidence was supplied, so nothing is proven")
        prompt = build_prompt(goal=goal, criteria=list(criteria or []), evidence=evidence)
        try:
            answer = call(prompt) or ""
        except Exception as e:                     # an error is not an endorsement
            return _fail(f"the verifier could not be reached: {e}")
        return parse(answer)

    return verify


def unavailable(reason: str) -> Callable[..., Verdict]:
    """The verifier when there is none. Always FAIL, and says why."""

    def verify(**_: Any) -> Verdict:
        return _fail(f"no independent verifier is available: {reason}")

    return verify


def build_prompt(*, goal: str, criteria: List[str], evidence: str) -> str:
    lines = [_CONTRACT, "", f"GOAL: {goal}"]
    if criteria:
        lines.append("CRITERIA — every one must be met:")
        lines.extend(f"  - {c}" for c in criteria)
    else:
        # a stale plan's criteria are withheld; the goal still stands
        lines.append("CRITERIA: none were supplied — judge against the goal alone.")
    lines += ["", "VISIBLE EVIDENCE:", evidence]
    return "\n".join(lines)


def parse(answer: str) -> Verdict:
    text = (answer or "").strip()
    m = re.match(r"^\s*(PASS|FAIL)\b[:\s-]*(.*)$", text, re.I | re.S)
    if not m:
        return _fail(f"the verifier's answer could not be read as a verdict: "
                     f"{text[:120]!r}")
    state = m.group(1).upper()
    why = (m.group(2) or "").strip()
    return {"state": state, "why": why}


def _default_run(argv, prompt: str, timeout: float):
    import subprocess
    proc = subprocess.run(argv, input=prompt, capture_output=True, text=True,
                          timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


def claude_verifier(*, model: Optional[str] = None, timeout: float = 180.0,
                    run=_default_run) -> Callable[..., Verdict]:
    """A verifier that runs the local Claude CLI headlessly.

    A separate process with a fixed contract is real independence of *judgment*
    from the session that did the work. When it is the same engine, `verify()`
    records `independent: False` rather than pretending otherwise.
    """

    def call(prompt: str) -> str:
        argv = ["claude", "-p"] + (["--model", model] if model else [])
        code, out, err = run(argv, prompt, timeout)
        if code != 0:
            raise RuntimeError((err or out or "the verifier exited non-zero").strip()[:200])
        return out

    return model_verifier(call)


def chosen_engine(*, which: Callable[[str], Optional[str]] = None,
                  has_api_key: Optional[Callable[[], bool]] = None) -> Optional[str]:
    """Which judge this machine can actually reach.

    An unreachable judge fails everything, which is safe and useless. So prefer
    an engine that is installed here over one that only exists in config.
    """
    import shutil
    which = which or shutil.which
    if which("claude"):
        return "claude"
    if which("codex"):
        return "codex"
    if has_api_key is None:
        has_api_key = _openai_key_present
    return "openai" if has_api_key() else None


def _openai_key_present() -> bool:
    try:
        from ai4science.llm.openai_compat import resolve_key
        return bool(resolve_key("openai"))
    except Exception:
        return False


def default_verifier(model: Optional[str] = None, *, which=None,
                     has_api_key=None) -> Callable[..., Verdict]:
    """The best judge this machine can reach — or an honest refusal."""
    engine = chosen_engine(which=which, has_api_key=has_api_key)
    if engine == "claude":
        return claude_verifier(model=model)
    if engine == "openai":
        from ai4science.llm.openai_compat import chat

        def call(prompt: str) -> str:
            text, _ = chat("openai", [{"role": "user", "content": prompt}], model=model)
            return text

        return model_verifier(call)
    return unavailable("no verifier engine is installed or configured here")


def _fail(why: str) -> Verdict:
    return {"state": "FAIL", "why": why}

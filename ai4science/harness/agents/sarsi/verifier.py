"""The independent verifier — the only component here that may rule.

Its contract is deliberately narrow: **judge only visible evidence; an unproven
claim fails.** `CAP`, the ledgers and the worker all *report*; none of them may
issue a positive verdict.

**Three verdicts, and the third is the point:**

| Situation | Verdict | Why |
|---|---|---|
| the model says PASS, with evidence | `PASS` | the only way through |
| the model says FAIL | `FAIL` | with its reason kept, because the reason is *used* |
| the answer cannot be parsed | `UNVERIFIED` | an unparseable verdict is not a verdict |
| the model call raises | `UNVERIFIED` | an error is not a judgment |
| no verifier is configured at all | `UNVERIFIED` | nothing judged this |
| there is no visible evidence | `UNVERIFIED` | nothing was shown, so nothing was judged |

`UNVERIFIED` is **never a pass** — that part is unchanged, and `is_pass()` is
the only thing anything downstream should ask.

Collapsing it into `FAIL` looks safe and is not. `FAIL` is a *judgment*, and its
reason is fed back into the session as the next instruction. With no verifier
configured, the session was being told *"the verifier says this is not done yet:
no independent verifier is available"* and asked to address it — a correction
nobody made, about a problem it cannot fix. Separating the two costs one
constant and removes a whole class of nonsense instruction.

The empty-evidence case still never reaches the model: paying for a call to
learn that nothing was shown is waste.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Sequence

Verdict = Dict[str, Any]

PASS = "PASS"
FAIL = "FAIL"
#: No judgment happened — distinct from a judgment that the work is wrong.
UNVERIFIED = "UNVERIFIED"

_CONTRACT = (
    "You are an independent verifier. You did not do this work and you do not "
    "advocate for it.\n"
    "Judge ONLY the visible evidence below. An unproven claim FAILS — a "
    "statement that something was done is not evidence that it was.\n"
    "Every criterion must be satisfied by that evidence for a PASS.\n"
    "Answer on one line, starting with exactly PASS or FAIL, then a colon and "
    "your reason."
)


def is_pass(verdict: Verdict) -> bool:
    """The only question anything downstream should ask about a verdict."""
    return str((verdict or {}).get("state", "")).upper() == PASS


def was_judged(verdict: Verdict) -> bool:
    """Did a judge actually look? `UNVERIFIED` means no.

    Everything that *acts* on a FAIL — feeding the reason back, steering
    against it — must ask this first, or it acts on a judgment nobody made.
    """
    return str((verdict or {}).get("state", "")).upper() in (PASS, FAIL)


def model_verifier(call: Callable[[str], str]) -> Callable[..., Verdict]:
    """Wrap a single-prompt model call into a verifier."""

    def verify(*, goal: str, criteria: Sequence[str], evidence: str) -> Verdict:
        if not (evidence or "").strip():
            return _unverified("nothing visible was supplied, so nothing was judged")
        prompt = build_prompt(goal=goal, criteria=list(criteria or []), evidence=evidence)
        try:
            answer = call(prompt) or ""
        except Exception as e:                     # an error is not a judgment
            return _unverified(f"the verifier could not be reached: {e}")
        return parse(answer)

    return verify


def unavailable(reason: str) -> Callable[..., Verdict]:
    """The verifier when there is none. Never a pass, and never a judgment."""

    def verify(**_: Any) -> Verdict:
        return _unverified(f"no independent verifier is available: {reason}")

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


#: A verdict LINE: begins with PASS or FAIL as a standalone token. The negative
#: lookahead is the whole fix — `PASS/FAIL` is not a verdict, it is the word
#: "verdict", and a live run recorded a task VERIFIED off an answer that said
#: `PASS/FAIL judgment on visible evidence only…` and then FAILED it two lines
#: down. Matching the first word of a narration is not reading a verdict.
_VERDICT_LINE = re.compile(r"^(PASS|FAIL)(?![\w/|-])[:\s]*(.*)$", re.I)


def parse(answer: str) -> Verdict:
    """Read the verdict out of the answer — by its verdict LINE, not its first
    word, and never by guessing when the answer says two things."""
    text = (answer or "").strip()
    found = []
    for line in text.splitlines():
        m = _VERDICT_LINE.match(line.strip())
        if m:
            found.append((m.group(1).upper(), (m.group(2) or "").strip()))
    if not found:
        return _unverified(f"the verifier's answer could not be read as a "
                           f"verdict: {text[:120]!r}")
    states = {state for state, _ in found}
    if len(states) > 1:
        # It said both. Picking one would be inventing a judgment; saying
        # nothing was decided is the truth.
        return _unverified(f"the verifier's answer gave more than one verdict: "
                           f"{sorted(states)}")
    state, why = found[0]
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
    return {"state": FAIL, "why": why}


def _unverified(why: str) -> Verdict:
    """Nothing judged this. Not a pass, and not a finding about the work."""
    return {"state": UNVERIFIED, "why": why}

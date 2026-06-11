"""Real OpenAI codex engine REPL — `ai4science chat --mode codex`.

Drives the installed **codex CLI** (`codex exec --json`) — the genuine product
agentic loop: OpenAI's own prompts, shell + apply_patch tools, AGENTS.md
project memory, sandboxing, session resume. Not a re-implementation.

The PWM layer wraps around it:
  • ``gate.check()`` before each turn; ``gate.charge()`` after, metered from
    the ``turn.completed`` usage event (same pricing table as the native
    harness);
  • ``/feedback`` intercepted locally (sustenance path);
  • MCP tool uses logged via ``gate.post_usage`` (agent-mining).

GPU tools: the ``ai4science`` MCP server (compute_providers / compute_dispatch
/ compute_result) is registered with codex globally (``codex mcp add``).
**Upstream limitation** (openai/codex #24135): ``codex exec`` auto-cancels MCP
tool calls non-interactively and no config key authorizes them. Set
``AI4SCIENCE_CODEX_GPU=1`` to run with
``--dangerously-bypass-approvals-and-sandbox`` — an explicit opt-in that also
disables codex's own shell sandbox for the session. AI4Science's paid-dispatch
guard still applies independently (``AI4SCIENCE_COMPUTE_AUTOCONFIRM``), so even
opted-in sessions cannot spend GPU PWM without a second explicit consent.

Fallback: ``commands/chat.py`` routes to the native harness when the codex CLI
or login is missing.
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from ai4science.harness.pwm_gate import PwmGate
from ai4science.harness.sdk_repl import _clean_input

AGENT_NAME = "codex"
BILLING_MODEL = "gpt-5.5"        # codex CLI default tier; matches the native adapter


def codex_engine_available() -> Tuple[bool, str]:
    """Can the real codex engine run here? (CLI on PATH + ChatGPT login.)"""
    if not shutil.which("codex"):
        return False, "codex CLI not on PATH — npm i -g @openai/codex then `codex login`"
    try:
        from ai4science.harness.adapters import codex_creds
        if not codex_creds.codex_available():
            return False, "no ChatGPT/codex login — run `codex login`"
        if codex_creds.codex_token_expired():
            return False, "codex login expired — run `codex exec \"ok\"` or `codex login`"
    except Exception:
        pass
    return True, ""


def handle_event(line: str, state: dict) -> Optional[str]:
    """Parse one JSONL event from `codex exec --json`. Mutates state
    (thread_id, usage, tools) and returns text to display, if any."""
    try:
        ev = json.loads(line)
    except (ValueError, TypeError):
        return None
    t = ev.get("type")
    if t == "thread.started":
        state["thread_id"] = ev.get("thread_id")
        return None
    if t == "turn.completed":
        state["usage"] = ev.get("usage") or {}
        return None
    if t == "item.completed":
        item = ev.get("item") or {}
        it = item.get("type")
        if it == "agent_message":
            return item.get("text") or ""
        if it == "command_execution":
            cmd = (item.get("command") or "")[:90]
            return f"[tool] shell: {cmd}"
        if it == "mcp_tool_call":
            name = item.get("tool") or "?"
            state.setdefault("tools", []).append(name)
            err = (item.get("error") or {}).get("message") if item.get("error") else None
            return f"[tool] {name}" + (f" (failed: {err})" if err else "")
        if it in ("file_change", "patch_apply", "patch"):
            return "[tool] apply_patch"
    return None


def _pwm_for(usage: dict) -> float:
    from ai4science.llm import pricing
    u = {"input": usage.get("input_tokens") or 0,
         "output": usage.get("output_tokens") or 0}
    return round(pricing.price_call(BILLING_MODEL, u)["pwm"], 6)


def _provider_wallet() -> Optional[str]:
    try:
        from ai4science.llm import routing
        return routing._select_source("openai")[2]
    except Exception:
        return None


def _turn_cmd(prompt: str, *, thread_id: Optional[str], read_only: bool,
              model: Optional[str], gpu_optin: bool, auto_yes: bool = False) -> list:
    cmd = ["codex", "exec"]
    if thread_id:
        cmd += ["resume", thread_id]
    cmd += ["--json", "--skip-git-repo-check"]
    if read_only:
        cmd += ["-s", "read-only"]
    elif gpu_optin or auto_yes:
        # --yes = the user already granted full-auto trust → codex's bypass
        # mode. This is ALSO the only way exec can run MCP/GPU tools (upstream
        # #24135) and sidesteps broken-bwrap hosts. The PWM paid-dispatch
        # guard still gates GPU spending independently (AUTOCONFIRM).
        cmd += ["--dangerously-bypass-approvals-and-sandbox"]
    else:
        cmd += ["--full-auto"]
    if model:
        cmd += ["-m", model]
    cmd.append(prompt)
    return cmd


def run_codex_repl(workspace: Path, *, auto_yes: bool = False,
                   read_only: bool = False, model: Optional[str] = None) -> None:
    gate = PwmGate.from_env()
    if gate.enabled:
        print("[harness] PWM gate ON — each turn is charged to the provider in PWM",
              flush=True)
    gpu_optin = str(os.environ.get("AI4SCIENCE_CODEX_GPU", "")).strip().lower() in (
        "1", "true", "yes", "on")
    full_trust = gpu_optin or auto_yes
    print(f"[harness] codex mode — REAL OpenAI codex engine (codex exec --json"
          f"{'; full-trust: codex sandbox off, GPU MCP on' if full_trust else ''}). "
          f"GPU tools via the ai4science MCP server"
          f"{'' if full_trust else ' (use --yes or AI4SCIENCE_CODEX_GPU=1 — upstream #24135)'}. "
          f"/feedback /exit are local.", flush=True)

    sid = secrets.token_hex(4)
    thread_id: Optional[str] = None
    n = 0
    is_tty = sys.stdin.isatty()
    while True:
        try:
            if is_tty:
                from ai4science.harness import tui
                line = tui.read_input("❯ ", "codex")
            else:
                line = sys.stdin.readline()
                if not line:
                    break
                print(f"❯ {line.rstrip()}", flush=True)
        except (EOFError, KeyboardInterrupt):
            break
        line = _clean_input(line)
        if not line:
            continue
        low = line.lower()
        if low in ("/exit", "/quit", "/q", "exit", "quit", "q", ":q"):
            break
        if low in ("/help", "/?"):
            print("[harness] local: /model [name]  /feedback <text>  /exit — "
                  "everything else goes to the codex engine.", flush=True)
            continue
        if low.startswith("/model"):
            arg = line[len("/model"):].strip()
            if not arg:
                print(f"[harness] model: {model or '(codex default)'} — "
                      f"switch with /model <id> (e.g. gpt-5.5, gpt-5.5-codex)",
                      flush=True)
            else:
                model = arg
                print(f"[harness] model → {model} (next turns use -m {model})",
                      flush=True)
            continue
        if low.startswith("/feedback"):
            arg = line[len("/feedback"):].strip()
            if not arg:
                print("[harness] usage: /feedback <your experience + how to improve "
                      "codex>", flush=True)
                continue
            if not gate.enabled:
                print("[pwm] feedback needs the PWM gate on "
                      "(AI4SCIENCE_PWM_GATE=1 + login --pwm).", flush=True)
                continue
            ok, status = gate.post_feedback(agent_name=AGENT_NAME, text=arg)
            note = (status if ok and str(status).startswith("accepted")
                    else status if any(str(status).startswith(k) for k in
                                       ("use_agent_first", "balance_not_low",
                                        "need_more_usage"))
                    else "program full (first-N guard)" if status == "program_full"
                    else f"failed ({status})")
            print(f"[pwm] feedback for {AGENT_NAME}: {note}", flush=True)
            continue

        allowed, reason = gate.check()
        if not allowed:
            print(reason, flush=True)
            continue

        n += 1
        state: dict = {}
        cmd = _turn_cmd(line, thread_id=thread_id, read_only=read_only,
                        model=model, gpu_optin=gpu_optin, auto_yes=auto_yes)
        from ai4science.harness.spinner import Spinner
        spin = Spinner("thinking").start()   # shining star while codex works
        try:
            proc = subprocess.Popen(cmd, cwd=str(workspace),
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True)
            assert proc.stdout is not None
            for raw in proc.stdout:
                out = handle_event(raw, state)
                if out:
                    spin.stop()
                    print(out, flush=True)
                    spin.start("thinking")
            spin.stop()
            proc.wait(timeout=30)
        except KeyboardInterrupt:
            spin.stop()
            proc.kill()
            print("\n[harness] turn interrupted", flush=True)
            continue
        except Exception as e:
            print(f"[harness] codex engine error: {type(e).__name__}: {e}", flush=True)
            continue
        thread_id = state.get("thread_id") or thread_id

        if gate.enabled and state.get("usage"):
            pwm = _pwm_for(state["usage"])
            if pwm > 0:
                ok, creason = gate.charge(
                    pwm, _provider_wallet(),
                    purpose=f"ai4science:{AGENT_NAME}:{BILLING_MODEL}",
                    idempotency_key=f"{sid}:{n}")
                if not ok:
                    print(creason, flush=True)
            from ai4science.harness.pwm_gate import BASE_TOOLS
            for t in {t for t in state.get("tools", []) if t.lower() not in BASE_TOOLS}:
                gate.post_usage(contribution_id=t, agent_name=AGENT_NAME,
                                turn_id=f"{sid}:{n}")

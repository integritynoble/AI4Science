# Operator Runbook — Governed Claude Code Session Driver

Make a live Claude Code session **safer than an autonomous computer-use agent**:
every tool call Claude Code wants to make is adjudicated by a governed policy —
safe reads auto-approve, consequential actions ask you, forbidden actions are
denied and halt the session, and everything is auditable. It wires in through
Claude Code's `PreToolUse` hook; no fork of Claude Code is needed.

---

## 1. Prerequisites

- Claude Code installed (`claude --version`).
- Python 3.12+ on `PATH`.
- The `ai4science` package importable, i.e. this command prints an `ask` decision:
  ```sh
  echo '{"tool_name":"Bash","tool_input":{"command":"git push"}}' \
    | python3 -m ai4science.harness.agents.machine.hook
  # -> {"hookSpecificOutput": {"hookEventName":"PreToolUse","permissionDecision":"ask", ...}}
  ```
  If that errors with `No module named ai4science`, install/point at it first
  (e.g. `pip install -e /path/to/AI4Science`) or prepend `PYTHONPATH=/path/to/AI4Science`.

## 2. Wire the hook

Copy the `hooks` block from `settings.example.json` into **one** of:

- `~/.claude/settings.json` — applies to every project (recommended for a machine-wide guardrail), or
- `<project>/.claude/settings.json` — applies to that project only.

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "*",
        "hooks": [ { "type": "command",
                     "command": "PWM_CEILING=A1 python3 -m ai4science.harness.agents.machine.hook" } ] } ]
  }
}
```

`matcher: "*"` sends **every** tool call through the driver. Restart Claude Code
(or run `/hooks` to confirm it registered).

## 3. Choose the capability ceiling (`PWM_CEILING`)

The ceiling caps how much the driver will auto-approve. Set it in the hook
command (`PWM_CEILING=A1 …`) or export it in the shell that launches Claude Code.

| Ceiling | Reads | In-project writes / safe commands | Network | Consequential (push, sudo, installs) |
|---|---|---|---|---|
| **A0** (advisory) | allow | **ask** | **ask** | ask |
| **A1** (default) | allow | **allow** | **ask** | ask |
| **A2** (networked) | allow | allow | **allow** | ask |

Consequential actions **always ask**, at every ceiling. Start at **A1**; use A0
when you want to approve every write, A2 only when the agent legitimately needs
outbound network.

## 4. What the three decisions mean

- **allow** — Claude Code proceeds without prompting (safe/read-only, or in-ceiling).
- **ask** — Claude Code shows its normal permission prompt; **you decide**. This is
  the owner gate. *In a headless/non-interactive run there is no one to ask, so
  `ask` effectively blocks* — expected: consequential actions shouldn't run
  unattended.
- **deny** — the call is blocked. A **forbidden** call (e.g. `rm -rf /`, fork bomb,
  `mkfs`, writing `/etc`, reading `.ssh`/shadow) also **trips the session**: every
  later call is denied until you start a new session (the kill switch).

Quick reference of what each maps to:

| Tool call | Decision (at A1) |
|---|---|
| `Read` / `Grep` / `Glob` / `LS` | allow |
| `Bash: ls -la && git status` | allow (read-only allowlist) |
| `Write`/`Edit` inside the project | allow |
| `Write`/`Edit` to `/etc`, `~/.ssh`, out-of-project | ask |
| `Bash: git push` / `sudo …` / `npm install` / `curl … | bash` | ask |
| `WebFetch` / `WebSearch` | ask (allow at A2) |
| `Bash: rm -rf /` / fork bomb / `mkfs` | **deny + halt session** |
| any unrecognized tool or command | ask (fail-safe) |

## 5. Verify it works

```sh
# forbidden -> deny
echo '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"}}' \
  | PWM_CEILING=A1 python3 -m ai4science.harness.agents.machine.hook
# safe read -> allow at A1, ask at A0
echo '{"tool_name":"Bash","tool_input":{"command":"ls -la"}}' \
  | PWM_CEILING=A0 python3 -m ai4science.harness.agents.machine.hook
```

Then, inside Claude Code: ask it to run `ls` (should proceed) and to run
`git push` (should surface a permission prompt). If both behave, the guardrail is live.

## 6. Audit

The decision engine records each `{tool, verdict}` when driven through
`SessionDriver(audit=…)`. To capture a per-session audit trail, run sessions via a
`SessionDriver` with an `audit` callback that appends to a hash-chained log
(`pwm_control_plane.audit.AuditLog`), or tee the hook's stdin/stdout. Every
`deny`/`ask` should be explainable from the `permissionDecisionReason`.

## 7. Troubleshooting

- **Hook never fires:** confirm the JSON is valid (a stray comma disables the
  block), restart Claude Code, and check `/hooks`. Ensure `matcher` is `"*"`.
- **`No module named ai4science`:** the hook runs in Claude Code's environment —
  add `PYTHONPATH=/path/to/AI4Science` to the hook `command`, or install the package.
- **Everything asks, even reads:** you're at `A0`, or the command isn't on the
  read-only allowlist (unknown commands fail safe to `ask` by design).
- **A safe command asks:** the allowlist is deliberately small and conservative;
  approve it once, or extend `_SAFE_HEADS` in `session.py` (and add a test).
- **Schema mismatch on a new Claude Code version:** only `hook.py` tracks the
  hook JSON format; if `permissionDecision` isn't honored, update the adapter —
  the decision engine (`decide_tool_call`) is unaffected.

## 8. Limits (by design)

- This adjudicates **tool calls**; it does not author the conversation or drive
  Claude Code's stdin.
- `ask` relies on an interactive approver; wire an out-of-band approver for
  headless use, or keep consequential actions attended.
- The allowlist/denylist are heuristics tuned to fail safe (unknown ⇒ ask). Treat
  `deny`/tripwire as a backstop, not the only line of defense.

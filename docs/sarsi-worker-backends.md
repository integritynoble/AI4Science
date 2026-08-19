# sarsi-worker backend combinations

Compares how well the ai4science harness works when sarsi-worker is paired
with each of the three openclaw session agents.

## Summary

| Combination | Drivable | ACP works | Governance ceiling | Brief format | Verdict |
|---|---|---|---|---|---|
| sarsi-worker + **sarsi-claude** | ✓ | ✓ | Full | Preserved | Production-ready |
| sarsi-worker + **sarsi-ai4sci** | ✓ | ✓ | Weak (auto-yes) | Newlines → spaces | Experimental |
| sarsi-worker + **sarsi-open** | ✓ | ✓ | Limited (no hook) | Preserved | Works, niche use |

---

## sarsi-worker + sarsi-claude (`spec: "claude-code"`)

**Verdict: Production-ready (current default)**

- `"claude-code"` is in `DRIVABLE_SPECS` ✓
- `OPENCLAW_ACP_IDS["sarsi-worker"] = "sarsi-claude"` — harness uses
  `openclaw_acp_runtime("sarsi-claude")` ✓
- Transport: `session/prompt` JSON-RPC → openclaw gateway → Claude Code TUI
  in tmux pane
- Kickoff delivery: round-trip ACP (no screen-reading); on failure,
  `rt.resume()` + re-brief at first unverified phase ✓
- `operator.py` recognises `❯` prompt prefix and `"esc to interrupt"` busy
  marker ✓
- Governance hook receives declared writable paths; ceiling changes via
  `supervisor.update()` propagate immediately ✓
- Plan phases, `collect_plan`, `_verify_phase` fully supported ✓

---

## sarsi-worker + sarsi-ai4sci (`spec: "general-purpose"`)

**Verdict: Experimental**

- `"general-purpose"` is in `DRIVABLE_SPECS` ✓
- `OPENCLAW_ACP_IDS["sarsi-ai4sci"] = "sarsi-ai4sci"` — uses
  `openclaw_acp_runtime("sarsi-ai4sci")` ✓
- Transport: `session/prompt` → gateway → `ai4sci-run.sh` →
  `python -m ai4science.harness.acp` → spawns `ai4science chat --mode ai4sci`
  per turn with `--resume <id>` for continuity
- **Newline flattening**: the ACP server collapses `\n` to spaces (documented
  in `server.py`). Multi-line briefs lose paragraph structure.
- **Governance ceiling**: `AUTO_YES=1` is required because there is no TTY.
  This bypasses the interactive permission prompt the governance hook normally
  raises, so ceiling enforcement is weaker.
- `operator.py` recognises `┃` prompt prefix ✓ but pane-reading is bypassed
  for ACP sessions anyway.
- Good fit for research/analysis tasks that don't need strict write governance.

---

## sarsi-worker + sarsi-open (`spec: "opencode"`)

**Verdict: Works, niche use**

- `"opencode"` is in `DRIVABLE_SPECS` ✓
- `OPENCLAW_ACP_IDS["sarsi-open"] = "sarsi-open"` — uses
  `openclaw_acp_runtime("sarsi-open")` ✓
- Transport: `session/prompt` → gateway → `opencode acp` subprocess —
  opencode speaks ACP natively, clean protocol match ✓
- Kickoff delivery: same round-trip ACP path as sarsi-claude ✓
- `operator.py` recognises `┃` prompt prefix and `"esc interrupt"` busy
  marker ✓
- **Governance ceiling**: opencode has no ai4science governance hook, so
  `supervisor.update()` ceiling changes do not propagate.
- Some operator pattern matching was written for Claude Code's output style
  (`Bash command` vs opencode's `$ <cmd>`); minor pane-reading gaps.
- Best for fast coding/scripting tasks where opencode's strengths matter and
  governance headroom is already set correctly at session start.

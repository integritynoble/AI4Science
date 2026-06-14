# AI4Science Plug-in Standard

How anyone contributes an **agent** or **tool** to AI4Science, tests it by
embedding it into the `research` agent (or any other), and earns PWM when others
use it. Plug-ins are pure-data manifests; tool code plugs in as an MCP server.

---

## 0. The loop at a glance

```bash
# 1. Get the code from GitHub
curl -fsSL https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.sh | bash

# 2. Write a manifest (agent or tool) — see §2
$EDITOR my-tool.json

# 3. Log in (testing spends PWM, like real usage)
ai4science login

# 4. Embed it into the research agent and test it
ai4science plugins test ./my-tool.json --into research

# 5. Publish to the gallery (browser) and let others install it
#    upload at https://physicsworldmodel.org/agents/contribute
ai4science plugins pull my-tool        # anyone, anywhere
```

---

## 1. Install from GitHub

The CLI lives at **github.com/integritynoble/AI4Science**. The installer makes an
isolated venv under `~/.ai4science` and links the `ai4science` command:

```bash
curl -fsSL https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.sh | bash
# or, from a clone:
git clone https://github.com/integritynoble/AI4Science && cd AI4Science
pip install .
```

Verify: `ai4science version`.

---

## 2. The manifest

One file per plug-in, **JSON or TOML**, dropped in the plugins dir
(`AI4SCIENCE_PLUGINS_DIR`, default `~/.ai4science/plugins/`) or passed to
`plugins test`. Two kinds:

| Field | Required | Applies to | Meaning |
|-------|----------|-----------|---------|
| `kind` | yes | both | `"agent"` or `"tool"` |
| `name` | yes | both | unique id (alnum, `-`/`_`) |
| `title` | yes | both | short human label |
| `description` | yes | both | one line (shown in the mode menu / dispatch enum) |
| `tier` | no | both | `open` or `science` (default `science`) |
| `wallet` | no | both | PWM address that charges for use / earns |
| `price_pwm` | no | both | per-use price you set (0 = free) |
| `mcp_servers` | no | both | external MCP servers that provide the tool code |
| `capabilities` | no | agent | built-in bundles or other tool plug-ins to include |
| `system_prompt` | no | agent | the agent's instructions |
| `keywords` | no | agent | extra search terms for `/mode` |
| `allow_as_subagent` | no | agent | may other agents dispatch to it (default true) |
| `category` | no | agent | `core` / `specific` (default `specific`) |
| `attach_to` | no | tool | agents that auto-receive this tool bundle |

### Agent example (`my-agent.json`)
```json
{
  "kind": "agent",
  "name": "spectral-pro",
  "title": "Spectral Pro",
  "description": "Snapshot spectral-imaging specialist.",
  "tier": "science",
  "capabilities": ["pwm-data", "ci-algorithms", "compute-providers"],
  "system_prompt": "Ground every claim in registered PWM solutions; preview cost before any paid dispatch.",
  "wallet": "0xYOUR_WALLET",
  "price_pwm": 3.0,
  "allow_as_subagent": true
}
```

### Tool example (`my-tool.json`)
```json
{
  "kind": "tool",
  "name": "denoise-suite",
  "title": "Denoise Suite",
  "description": "Image-denoising tools for any science agent.",
  "mcp_servers": [{ "name": "denoise", "command": "python", "args": ["-m", "denoise_suite.mcp"] }],
  "attach_to": ["research", "computational-imaging"],
  "wallet": "0xYOUR_WALLET",
  "price_pwm": 1.0
}
```

---

## 3. Capabilities (built-in bundles)

An agent lists bundle names in `capabilities`. Built-ins:

| Bundle | Tools |
|--------|-------|
| `pwm-actions` | pwm_status, pwm_validate, pwm_judge_cassi, pwm_lookup_artifact |
| `pwm-data` | pwm_principles / benchmarks / solutions / overview (read-only registry) |
| `ci-algorithms` | ci_modalities, ci_algorithms, ci_algorithm_info, ci_run_algorithm |
| `compute-providers` | compute_providers, compute_dispatch, compute_result |
| `onboarding` | onboard_* (author + submit PWM artifacts) |
| `paper-review` | paper_review |
| `computational-imaging` | cassi_solutions / forward_check / dispatch / result |

A **tool plug-in** registers its `name` as a new bundle, so other agents can list
it in `capabilities` too (or get it via `attach_to`).

---

## 4. Tools plug in as MCP servers

Tool **code** never runs in-process. List one or more MCP servers under
`mcp_servers`; AI4Science starts a client per server and namespaces the tools
`mcp__<server>__<tool>`. Build MCP servers with FastMCP (Python) or the MCP
TypeScript SDK.

---

## 5. Wallet & charging

Set `wallet` and `price_pwm`. When the PWM gate is on, a confirmed paid use:
- **charges** the caller `price_pwm`, credited to your `wallet` (marketplace fee);
- **logs usage**, so the weekly agent-pool emission also pays you
  (`weight = usage × quality`, where `quality` comes from an A/B improvement eval).

Off by default — development and `--free` tests run free.

---

## 6. Embed & test

`plugins test` loads ONLY your plug-in (isolated temp dir — non-destructive),
embeds it into the target agent, and opens a chat to try it:

```bash
ai4science login                                   # required (testing spends PWM)
ai4science plugins test ./my-tool.json             # → research (default)
ai4science plugins test ./my-agent.json --into paper
ai4science plugins test ./my-tool.json --free      # offline dev, no PWM
```

- A **tool** is attached to the target agent (its tools become the agent's tools).
- An **agent** is dispatchable by the target via the `task` tool — the target must
  be science-tier (the moat; see §8). `--into research` is the usual choice.
- Testing requires `ai4science login` and runs with the **PWM gate ON**, so it
  spends PWM exactly like real usage.

---

## 7. Publish & distribute

- **Upload** in the browser at `https://physicsworldmodel.org/agents/contribute`
  (validates, publishes to the gallery, registers your wallet to earn PWM).
- **Install** anywhere:
  ```bash
  ai4science plugins list                 # browse the gallery
  ai4science plugins pull <name>          # or --all
  ai4science plugins installed            # verify
  ```

---

## 8. Tiers & the moat

- `open` agents (`claude-code`, `codex`, `unified-LLM`) are the base coding
  assistants: **main-only** (never sub-agents), no PWM tools.
- `science` agents (`research`, `paper`, `computational-imaging`, and your
  plug-ins) reach PWM data + the reconstruction algorithm base, and compose each
  other as sub-agents.
- Plug-ins default to `science`, so a science main (e.g. `research`) can dispatch
  to them while base agents cannot. To test an agent plug-in, embed into a science
  agent.

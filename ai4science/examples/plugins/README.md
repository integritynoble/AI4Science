# Plug-in agents & tools

> Full spec: **[../../../PLUGIN_STANDARD.md](../../../PLUGIN_STANDARD.md)** (repo root).

Drop a manifest in your plugins dir and ai4science discovers it at startup — no
code PR. Default dir: `~/.ai4science/plugins/`; override with
`AI4SCIENCE_PLUGINS_DIR`.

## Test it against the research agent

```bash
ai4science login                                  # testing spends PWM
ai4science plugins test ./spectral-pro.agent.json --into research
ai4science plugins test ./denoise-suite.tool.json --into computational-imaging
ai4science plugins test ./spectral-pro.agent.json --free   # offline, no PWM
```

`plugins test` loads ONLY that plug-in (isolated temp dir), embeds it into the
target agent, requires login, and opens a chat with the PWM gate ON.

```bash
mkdir -p ~/.ai4science/plugins
cp spectral-pro.agent.json ~/.ai4science/plugins/
ai4science chat --mode research        # `task` can now dispatch to spectral-pro
```

## Install a published plug-in

Plug-ins uploaded on physicsworldmodel.org are installable directly:

```bash
ai4science plugins list                # browse the gallery
ai4science plugins pull spectral-pro   # install one (or --all)
ai4science plugins installed           # verify your local dir
```

`pull` validates each manifest with the same parser the harness loads with, so a
bad manifest is never written. Override the source with `--base` and the target
dir with `--dir`.

## Two kinds

- **`"kind": "agent"`** → a full agent added to the registry. Dispatchable as a
  sub-agent by any science-tier main (the moat: base agents claude-code/codex/
  unified-LLM stay main-only and can't reach science plug-ins). Carries its own
  `wallet` + `price_pwm`.
- **`"kind": "tool"`** → a capability bundle backed by an MCP server. Any agent
  can list its `name` in `capabilities`; `attach_to` auto-injects it into the
  named existing agents with no edit.

## Tool code = MCP server

Manifests are pure data; tool **code** plugs in as an external MCP server (stdio)
listed under `mcp_servers`. ai4science builds a client per server and namespaces
its tools `mcp__<server>__<tool>`. Nothing runs in-process.

## Wallet & charging

Set `wallet` (a PWM address) and `price_pwm` (per-use price you choose). When the
PWM gate is on, a confirmed paid use debits the user and credits your wallet, and
logs agent-pool usage so the weekly emission also rewards you
(`w_k = usage × quality`). Off by default (dev/CI run free).

See `spectral-pro.agent.json` and `denoise-suite.tool.json`.

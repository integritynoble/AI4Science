# Installing AI4Science on a new computer

AI4Science isn't on PyPI yet, so you install from the git repo. Three
tiers depending on what you need:

| You want… | Install |
|---|---|
| The CLI + deterministic judge (init / validate / judge / package) | base |
| The chat agent (`ai4science chat`, sub-agents, MCP) | base + `[claude]` + the `claude` CLI |
| To run the tests / contribute | base + `[dev]` |

---

## Step 0 — Prerequisites

You need **Python ≥ 3.10** and **git**.

**Linux (Debian/Ubuntu)**
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

**macOS** (with [Homebrew](https://brew.sh))
```bash
brew install python git
```

**Windows** (PowerShell, with [winget](https://learn.microsoft.com/windows/package-manager/))
```powershell
winget install Python.Python.3.12 Git.Git
```

Check:
```bash
python3 --version    # Windows: python --version
git --version
```

---

## Step 1 — Get the code

```bash
git clone https://github.com/integritynoble/AI4Science.git
cd AI4Science
```

---

## Step 2 — Create a virtual environment

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
# if blocked once:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Your prompt should now show `(.venv)`.

---

## Step 3 — Install

```bash
pip install -e .
```

That's the full CLI. Verify:
```bash
ai4science --version
ai4science init demo
cd demo
ai4science validate
ai4science judge cassi --submission .
```

You should see a validation table (all `ok`) and a judge report.

---

## Step 4 (optional) — Enable the chat agent

`ai4science chat` (interactive REPL, sub-agents, MCP tools) is powered by
the Claude Agent SDK, which drives the `claude` CLI. Two extra pieces:

1. Install the SDK extra:
   ```bash
   pip install -e ".[claude]"
   ```
2. Install the `claude` CLI and authenticate (one of):
   ```bash
   npm install -g @anthropic-ai/claude-code     # needs Node.js
   claude login                                  # use a Claude Pro/Max/Team subscription
   #   — OR —
   export ANTHROPIC_API_KEY=sk-ant-...           # use an API key
   ```

Check what's available:
```bash
ai4science agents          # shows none / claude / codex availability
ai4science chat            # opens the REPL once claude is ready
```

No API key needed if you used `claude login` — it uses your subscription.

---

## Step 5 (optional) — Developer setup

```bash
pip install -e ".[dev]"
pytest                      # full test suite
```

---

## Quick reference

```bash
ai4science --help                       # all commands
ai4science init <name>                  # new contribution workspace
ai4science validate                     # check artifacts
ai4science judge cassi --submission .   # deterministic Physics Judge
ai4science chat                         # interactive agent (needs Step 4)
ai4science compute providers            # GPU compute providers
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ai4science: command not found` | The venv isn't active. Re-run the activate command from Step 2. |
| `python: command not found` (Linux/macOS) | Use `python3`. |
| Windows: emoji/box characters look broken | Fixed in current versions (UTF-8 is forced); update to latest `main`. |
| `claude agent not available` in chat | Do Step 4 — install the `claude` CLI and `claude login` (or set `ANTHROPIC_API_KEY`). |
| `pip install` compiles numpy slowly | Upgrade pip first: `pip install --upgrade pip`. |

For a GPU compute provider box, see [`SUBGPU_SETUP_WINDOWS.md`](SUBGPU_SETUP_WINDOWS.md).

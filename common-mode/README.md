# AI4Science common mode

AI4Science common mode is a small launcher around **unmodified OpenCode 1.18.34**.
It provides our command, research agent and defaults through configuration. Your
own LLM incurs **no AI4Science/PWM charge**; a third-party API provider can still
bill you under your own account. PWM inference is reserved for AI4SCI-07 and is
disabled here. This is development work for owner review, not a published release.

## Install

Obtain this complete `common-mode/` directory from a reviewed repository archive
or the owner's checkout. No public AI4Science installer endpoint is established
in this packet. These scripts require their adjacent files; do not pipe a lone
script into a shell. The repository's root install scripts belong to the existing
Python edition and are separate from this wrapper.

Linux / macOS:

```sh
sh common-mode/install.sh
# Or choose a fresh, absolute prefix:
sh common-mode/install.sh --prefix "$HOME/ai4science-common"
export PATH="$HOME/ai4science-common/bin:$PATH"
ai4science --version
```

Default prefix: `$HOME/.local/ai4science-common`. Add that prefix's `bin` to PATH
if using the default. Installation does not edit shell profiles or overwrite an
existing installation. Prefixes containing spaces work. Use the actual installed
launcher path or its directory in PATH; relocating it alone or symlinking it into
another directory is not supported. Move the entire prefix together.

Windows 10/11 (PowerShell 5.1+, x64 or arm64):

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\common-mode\install.ps1
# Optional fresh prefix:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\common-mode\install.ps1 -Prefix "$env:LOCALAPPDATA\AI4Science\Common Test"
$env:PATH = "$env:LOCALAPPDATA\AI4Science\Common Test\bin;$env:PATH"
ai4science.cmd --version
```

From MSYS2 or Git Bash, run the same `powershell.exe ... -File common-mode/install.ps1` command (`install.sh`
refuses these shells and points here), then call `ai4science.cmd` through `cmd //c` or run
`powershell.exe -NoProfile -File "$(cygpath -w PREFIX/bin/ai4science.ps1)" ...`.

Default prefix: `%LOCALAPPDATA%\AI4Science\Common`. `ai4science.cmd` starts a
fresh PowerShell process and forwards arguments. The execution-policy switch is
limited to that process; this does not change machine policy or bypass enterprise
application control. An administrator may need to approve execution on managed
machines. Scripts are not signed in this development packet.

**No user-installed Node, npm or git is needed for installation or the first
session.** OpenCode's native executable contains its runtime and package manager.
POSIX installation requires ordinary shell utilities, tar/gzip, curl or wget and
sha512sum/sha256sum or shasum. Windows needs its built-in `tar.exe`, PowerShell
web requests and archive/hash commands. Git is optional for upstream repository
features; local projects and the first conversation work without it.

Supported artifact selections: Linux x64 glibc/musl, Linux arm64 glibc, macOS
x64/arm64, Windows x64/arm64. x64 uses the upstream baseline executable, avoiding
an AVX2 requirement. Linux arm64 musl is rejected because the pinned ripgrep
release has no matching executable. Only abraham Linux x64 has been executed in
this packet; see [TESTING.md](TESTING.md) for the other platform procedures.

Installation downloads the checksum-pinned engine from `registry.npmjs.org`,
checksum-pinned ripgrep 15.1.0 from GitHub releases, and config-plugin dependencies
from npm. GitHub release downloads may redirect to GitHub's asset host. The
engine's package and version are locked in `artifacts.lock` / `opencode.version`;
release SHA-512 values are taken from npm's published integrity metadata.
`ripgrep.lock` contains GitHub's published SHA-256 release digests. Hash failures
stop before a prefix is created. The dependency graph is resolved by upstream
npm metadata and retained in the prefix's `package-lock.json`; it is not a fully
vendored, offline or bit-for-bit reproducible distribution.

OpenCode starts a background config dependency install even with no plugins.
During installation we temporarily use a no-op file plugin so its loader waits
for that dependency setup to finish. We then remove it and restore `plugin: []`.
The installed wrapper requires offline npm at runtime. Search is preinstalled so
OpenCode does not download ripgrep during a cold session. A failed installation
may leave a private partial prefix and diagnostics in `var/install.log`; inspect
or remove that prefix explicitly before retrying. Existing prefixes are refused.

## Use your own model

The default endpoint is `http://127.0.0.1:8000/v1`, with model ID `local` and a
non-secret local placeholder key. Nothing contacts an AI4Science inference
service. For a local OpenAI-compatible server, set its endpoint and model ID:

```sh
export AI4SCIENCE_BASE_URL=http://127.0.0.1:11434/v1
export AI4SCIENCE_MODEL=your-installed-model
ai4science run 'Explain the assumptions behind this experiment.'
```

For your own compatible API account, set `AI4SCIENCE_BASE_URL`,
`AI4SCIENCE_MODEL` and `AI4SCIENCE_API_KEY` through your environment/secret manager.
Use a genuine key only when needed; do not paste it into a command history or
commit it. On Windows the corresponding variables are `$env:AI4SCIENCE_BASE_URL`,
`$env:AI4SCIENCE_MODEL` and `$env:AI4SCIENCE_API_KEY`. The selectable model remains
`own-llm/local`; the ID sent to the server is `AI4SCIENCE_MODEL`.

Edit **PREFIX/var/config/opencode/opencode.json** for additional models or other
API-key providers. Add their IDs to `enabled_providers` and choose `model` and
`small_model` explicitly. Avoid automatic background calls to another provider
by keeping the small-model choice on your own endpoint. Provider definitions
use OpenCode's standard config schema. Do not enable Claude subscription OAuth;
ChatGPT subscription integration needs the separate review described in
[TERMS.md](TERMS.md). Upstream login plugins are disabled by default.

## Isolation and PWM extension

Config, sessions, stored auth, cache and state live under the installation's
`var/` tree. The wrapper sets **all four XDG roots**, its own config directory and
file, a private OpenCode home-discovery path, and a private managed-config path.
Setting only `OPENCODE_CONFIG_DIR` would still load other upstream global files.
Every installer engine check uses this same wrapper environment. The wrapper
clears **all inherited `OPENCODE_*` variables** before setting its private values,
including unknown/future upstream flags. It disables project config discovery,
external skills, Claude settings, login plugins, model-catalog fetching, LSP
downloads, sharing and automatic upgrades.
Inherited HTTP proxy variables are removed so requests use the configured model
endpoint directly.

Where a session works:

| Launch | Session folder | Project settings |
|---|---|---|
| `ai4science ...` | `PREFIX/var/config/opencode` (private) | none |
| `ai4science --workspace DIR ...` or `AI4SCIENCE_WORKSPACE=DIR` | `DIR` | off |
| `AI4SCIENCE_PROJECT_CONFIG=1 ai4science ...` | the current folder | loaded (explicit trust) |

Without either choice, the engine starts in its private config folder. That is the one place where the pinned
engine's newer (v2) config loader reads no project files: that loader ignores `OPENCODE_DISABLE_PROJECT_CONFIG`.

**Use `--workspace DIR` to work on a project.** The agent's files and tools are in `DIR`, and project settings stay
off. A hostile workspace was tested: its `opencode.json`, `.opencode/` folder (with plugin), `AGENTS.md` and MCP
command loaded no provider, model, instructions, plugin, agent or MCP server.

One upstream behaviour remains. The v2 loader still **opens** `opencode.json` and `.opencode/opencode.json` from
`DIR` up to the project root (the git root, or `/` outside git), and takes only `experimental.policies` (policy
statements such as provider access) from them. If that matters, make `DIR` its own git root. The walk then stops
at `DIR`.

`AI4SCIENCE_PROJECT_CONFIG=1` opts in to the current folder's whole project config, including its providers,
plugins and MCP servers. With `--workspace`, it applies to `DIR` instead. An explicit project/directory argument to
upstream commands also chooses an external workspace and may read its settings. Installation always forces the
private folder, even when the runtime opt-in is set.

### Non-interactive runs and the server

```sh
ai4science --workspace /path/to/task run --format json 'Solve the task described in problem.json.' </dev/null
AI4SCIENCE_SERVER_PASSWORD=... ai4science serve --port 4096   # HTTP basic auth, user "opencode"
```

- `run` reads a piped standard input as part of the message. Give it `</dev/null` (or `stdin=DEVNULL`) when
  nothing is piped, or it waits.
- The launcher clears every inherited `OPENCODE_*` variable, `OPENCODE_SERVER_PASSWORD` included. A server
  password is passed only as `AI4SCIENCE_SERVER_PASSWORD` (and optionally `AI4SCIENCE_SERVER_USERNAME`), which
  the agent's own commands do not inherit.
- A server serves any folder a client names (`?directory=`). Project settings stay off for those folders too.
- Settings for a whole run (permissions, the model, an MCP server) go in the install's private `opencode.json`.
  This is how AI4SCI-08's two E4 arms differ: one copy of the install each.

To opt in to providers or MCP servers, edit the private
`PREFIX/var/config/opencode/opencode.json` explicitly; global OpenCode settings
are never imported automatically. Project settings require the opt-in above.
No PWM proxy or ledger is installed.
In an explicitly selected workspace, ordinary project files can be indexed/read
as workspace data, and the agent can use authorized local tools. This wrapper is
configuration isolation, not an OS network sandbox.

OpenCode's managed macOS preferences cannot be disabled through a supported
setting. The POSIX launcher refuses Macs with an `ai.opencode.managed` profile
rather than merge it into our settings. The private home-discovery path and
managed-directory override use upstream test environment variables; these are
version-sensitive hooks covered by the Linux isolation test, not stable public
API guarantees.

The reserved MCP slot is `"mcp": {"pwm": {"enabled": false}}`. There is no URL,
command, credential, or process behind it. `"plugin": []` reserves the plugin
extension point. AI4SCI-07 must supply the reviewed, pinned plugin/MCP definition
and make PWM an explicit paid choice; this packet does not implement billing.

## Why a wrapper

A wrapper follows owner decision D11: keep upstream code intact and express our
behavior in settings, plugins and MCP. This reduces merge maintenance and keeps
engine attribution and MIT notices intact. Our name appears in the command,
version banner, conversation username and research-agent name. OpenCode has no
complete product-name/logo override; its own help/TUI branding remains visible.
The wrapper makes no claim of upstream endorsement and does not use its logo as
ours.

A fork would need owner review if a required behavior cannot be implemented with
config/plugin/MCP hooks: complete engine/TUI rebranding, a hard authentication
or network-enforcement boundary, or isolation after upstream removes the hooks
we rely on. A separate approved UI could sometimes solve the same requirement
without forking. Legal permission for a provider cannot be created by a fork.

Keep [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) with the engine. Installed
ripgrep notices live in `share/ripgrep/`; npm dependency notices stay with their
packages. Before any binary redistribution, audit the full upstream dependency
bundle and obtain the owner's release approval.

**Taking an OpenCode update** changes only `artifacts.lock` and `opencode.version`:

```sh
python3 common-mode/tools/pin_opencode.py 1.18.35       # from npm's published sha512 integrity
sh common-mode/tests/run_linux_ci.sh "$(mktemp -d)"     # every Linux check against the new engine
```

Before accepting an update, also review:
- the upstream source licence;
- the upstream hooks the launcher relies on (the private home/managed variables, the v2 config loader);
- `ripgrep.lock`.

**Rehearsed on 2026-10-03:**
- 1.18.34 was still the newest release, so I re-pinned the engine to 1.18.33.
- `pin_opencode.py 1.18.34` reproduces the committed lock byte for byte.
- With the 1.18.33 pin, the whole suite passed, and the installed engine reported 1.18.33.

Automatic updates and the direct `upgrade` command are disabled by the launcher. No release is published from
this folder.

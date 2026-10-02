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

By default the engine starts in `PREFIX/var/config/opencode`, its private global
config directory. This is deliberate: the pinned engine's newer config loader
reads project settings even when `OPENCODE_DISABLE_PROJECT_CONFIG=1`; it skips
project discovery only when opened in its global config directory. A default
session therefore does not use your shell's current project as its workspace.
To explicitly allow the current project's settings and workspace, set
`AI4SCIENCE_PROJECT_CONFIG=1` (`$env:AI4SCIENCE_PROJECT_CONFIG = '1'` on Windows).
That opts in to project config, including its providers, plugins and MCP servers.
An explicit project/directory argument to upstream commands likewise chooses an
external workspace and may read its settings. Installation always forces the
private directory, even when the runtime opt-in is set.

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

The pin has not been updated or rehearsed in this job. A later update must review
both lock files, the source license and isolation hooks, then repeat installation
and [the smoke checks](TESTING.md). Automatic updates and the direct `upgrade`
command are disabled by the launcher. Do not publish or push this packet.

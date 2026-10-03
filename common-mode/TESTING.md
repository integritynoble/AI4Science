# Installation and session checks

Use a disposable prefix and test account. Never copy real OAuth tokens or API
keys into fixtures. Python 3 is needed for these **developer test fixtures**, not
for users installing/running AI4Science. No Windows/macOS result is claimed yet.

## All Linux checks at once (CI)

```sh
sh common-mode/tests/run_linux_ci.sh "$(mktemp -d)"
```

It runs everything below that works on Linux, and makes no real model calls:
- static checks (shell syntax, JSON, ASCII-only PowerShell/cmd files, lock formats, PowerShell parse);
- the stub-engine launcher checks (`sh` and, with pwsh, `ai4science.ps1`);
- install and first-session isolation;
- workspace sessions;
- smoke (`--trace` only when strace is installed);
- `install.ps1` under pwsh.

The pinned engine and ripgrep archives are downloaded once and checked against the committed locks. The GitHub
workflow `.github/workflows/common-mode.yml` runs this script on `fleet/ai4sci-06-**` pushes and on pull requests
that touch `common-mode/`.

## Taking an OpenCode update

`python3 common-mode/tools/pin_opencode.py VERSION` rewrites `artifacts.lock` and `opencode.version` from npm's
published integrity data. Then run `run_linux_ci.sh`, and the Windows and macOS procedures below.

Rehearsal on 2026-10-03:
- re-pinning 1.18.34 reproduced the committed lock exactly;
- re-pinned to 1.18.33, all Linux checks passed and the installed engine reported 1.18.33;
- the pin was then kept at 1.18.34.

## Workspace sessions: the E4 common arm and the worker server (Linux)

```sh
python3 common-mode/tests/workspace_session.py --prefix PREFIX --output "$PWD/workspace-evidence"
```

A loopback fake model makes one scripted `write` tool call, then answers. The test checks:
- `ai4science --workspace DIR run --format json` (stdin closed) writes the file in `DIR`;
- `ai4science serve` with `AI4SCIENCE_SERVER_PASSWORD` answers 401 without the password and 200 with it, and a
  session created for `?directory=DIR` writes there;
- requests carry only the configured model ID, and no PWM tool is offered;
- a hostile `opencode.json`, `.opencode/` plugin, `AGENTS.md` and MCP command in and above `DIR` start nothing,
  contact nothing and never reach the model;
- only the two result files change;
- the install's private settings are unchanged.

A launcher that turned project settings on for `--workspace` fails this test (checked).

## install.ps1 and ai4science.ps1 under PowerShell 7 on Linux

```sh
python3 common-mode/tests/install_ps1_on_linux.py --output "$PWD/ps-evidence"
```

This runs the real `install.ps1` logic in a copied source tree, then a `--workspace` session through
`ai4science.ps1`. In the copy, one Windows lock line points at the pinned Linux engine repacked as `opencode.exe`.
`powershell.exe`, `tar.exe` and `ai4science.cmd` are shims.

It does **not** replace the Windows procedure below. It cannot show:
- Windows PowerShell 5.1's own behaviour, such as a redirected native stderr line becoming a terminating error
  (`install.ps1` now runs that step under `Continue` and checks the exit code);
- Windows paths;
- `cmd.exe` argument forwarding;
- the Windows engine binary.

## Install and first-session isolation regression (Linux)

```sh
python3 common-mode/tests/install_isolation.py --output "$PWD/isolation-evidence"
```

This installs into a fresh prefix containing spaces with a synthetic HOME,
XDG roots, hostile global/home/project configs, fake auth/state/cache, and
inherited `OPENCODE_*` overrides. A runtime project opt-in is also planted
during installation to verify the installer forces private mode. The hostile config supplies a provider and an
enabled local MCP command that would leave a marker. The very first session
uses the loopback fake chat-completions server; no real model is called.
Linux inotify is required and self-checked. Each phase must have zero reads,
opens, writes or creation events on protected global paths/project config
files, unchanged fixture trees, no hostile endpoint requests or MCP marker,
and only the private provider/disabled PWM slot in resolved settings.
Install must not call the model fixture. This does not trace all network traffic.
`--engine-archive` and `--ripgrep-archive` reuse local checksum-verified archives;
`--source` allows running the same regression against an exported baseline.

```sh
python3 common-mode/tests/launcher_environment.py --output "$PWD/environment-evidence"
```

The stub-engine check verifies removal of known and future upstream flags,
preservation of explicit model settings, the private default directory and
current-directory project opt-in, and propagation of a failed version probe.

## Automated Linux proof (abraham now, integrity-wsl later)

From the repository root:

```sh
proof=$(mktemp -d)
sh common-mode/install.sh --prefix "$proof/prefix"
"$proof/prefix/bin/ai4science" --version
python3 common-mode/tests/smoke.py "$proof/prefix" --trace --output "$proof/evidence"
# Also verify mapping a real server model name through the stable local alias:
python3 common-mode/tests/smoke.py "$proof/prefix" --trace --model-id science-test-model --output "$proof/custom-evidence"
```

`--trace` requires Linux strace. The harness uses only loopback, creates conflicting
OpenCode global/project configs and fake global OAuth auth, removes Node/npm/git
from runtime PATH, then checks the version, resolved config, model list and JSON
session output. It rejects even failed IPv4/IPv6 network attempts to anything
except the fixture's dynamically assigned `127.0.0.1` port, including DNS. File
traces must not read global OpenCode config/auth; fixture hashes must stay intact.
Default sessions start in the private directory; the external project configs
must not load. Explicit project opt-in is tested separately with the stub engine.
A successful session contains `AI4SCIENCE_LOCAL_OK`, all request models match the
chosen ID, and there are no PWM/ledger files. The title helper can make a second
request to the same server; that is expected.

`summary.json` and `requests.jsonl` contain no prompts or credentials. Raw traces
and session data remain in the private temporary evidence directory; do not
publish traces from real-key sessions. See [REPORT.md](REPORT.md) for the abraham
results and retained proof locations. integrity-wsl is deferred to a later job;
run this exact procedure there and record its host/architecture separately.

To prove **installation** also needs no Node/npm/git, create a temporary PATH
with symlinks to the OS shell utilities used by the installer (`sh`, `dirname`,
`uname`, `awk`, `grep`, `ldd`, `mktemp`, `cp`, `curl` or `wget`, `sha512sum`,
`sha256sum` or `shasum`, `tar`, `gzip`, `mkdir`, `chmod`, `cat`, `find`, `basename`,
`sed`, `id`, `env`). Run the installer with that PATH and an otherwise empty environment,
then run the harness against the resulting prefix. Do not add node/npm/git to it.

Negative checks: provide a deliberately altered engine archive using
`AI4SCIENCE_ARTIFACT`, or altered search archive using
`AI4SCIENCE_RIPGREP_ARTIFACT`; checksum failure must leave no prefix. Reinstalling
into any existing prefix must fail without changing any files. Both override
paths still require the committed checksum; they are useful for fleet caching.
`ai4science upgrade` must fail with exit 2, preserving the engine checksum.

## macOS procedure (not executed)

1. On x64 and Apple Silicon, use a fresh account/prefix with no Node/npm/git.
   Download a reviewed archive containing the entire `common-mode` directory.
   Run `sh common-mode/install.sh --prefix "$TMPDIR/ai4science-common-test"`.
   Confirm the platform package selected from the lock and that SHA checks pass.
2. Run `.../bin/ai4science --version`; expect the exact `opencode.version` pin.
   Run the Python harness **without** `--trace` (strace is Linux-specific). This
   checks configuration/session behavior and unchanged fixtures, but does not
   claim network or file-read tracing on macOS.
3. For independent network proof, start `tests/fake_openai.py --port 8000` in one
   terminal; set `AI4SCIENCE_BASE_URL=http://127.0.0.1:8000/v1` and run
   `ai4science run --format json 'Reply with exactly AI4SCIENCE_LOCAL_OK. Do not use tools.'`
   in another. Use a fresh prefix and macOS Instruments network tracing or an
   administrator's per-process network capture for the wrapper/engine and children.
   Exclude installer downloads from the session trace. Record only loopback model
   connections, no DNS/remote TCP attempts. A host-wide tcpdump alone is not enough
   to attribute unrelated traffic to this process.
4. Check `debug config`: AI4Science username/agent, only `own-llm`, no plugins,
   PWM disabled, sharing/update disabled. Seed **temporary account** global
   OpenCode config/auth with fake conflicting values; verify neither is changed
   and the resolved config ignores them. Use file tracing to check neither read.
5. Confirm no billing files, `upgrade` refusal, and no Node/npm/git invocations.
   Keep notices in `share/` and package licenses in `var/config/.../node_modules`.
   A managed `ai.opencode.managed` profile must cause a clear refusal; do not remove
   a real organization's profile for a test. Test this on a disposable managed Mac.
6. Record OS/CPU, commands, pin, output, trace summary and unresolved failures.

## Windows procedure (not executed)

1. Use Windows 10/11 x64 or arm64 and a disposable local account. Ensure Node/npm/
   git are absent from PATH. PowerShell 5.1 and `tar.exe` must be available. Extract
   the reviewed repository archive and run:

   ```powershell
   $TestRoot = Join-Path $env:TEMP ('ai4science-' + [guid]::NewGuid().ToString('N'))
   $Prefix = Join-Path $TestRoot 'prefix with spaces'
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\common-mode\install.ps1 -Prefix $Prefix
   & "$Prefix\bin\ai4science.cmd" --version
   ```

2. In another console, set `$TestRoot` to the same test-directory path as above,
   then start the developer fixture:

   ```powershell
   python .\common-mode\tests\fake_openai.py --port 8000 --log "$TestRoot\requests.jsonl"
   ```

   In the session console, run:

   ```powershell
   $env:AI4SCIENCE_BASE_URL = 'http://127.0.0.1:8000/v1'
   $env:AI4SCIENCE_MODEL = 'science-test-model'
   & "$Prefix\bin\ai4science.cmd" debug config
   & "$Prefix\bin\ai4science.cmd" models
   & "$Prefix\bin\ai4science.cmd" run --format json 'Reply with exactly AI4SCIENCE_LOCAL_OK. Do not use tools.'
   ```

   Expect exit 0 and a JSON text event containing `AI4SCIENCE_LOCAL_OK`. Requests
   must be `/v1/chat/completions` with model `science-test-model`; only `own-llm/local`
   is selectable. Inspect argv forwarding with a prompt containing spaces and the
   prefix containing spaces, from both cmd.exe and PowerShell.
3. Use Sysinternals Process Monitor filtered to the launched PowerShell, native
   OpenCode and child PIDs for TCP/UDP, file-read and process-create events. Start
   capture **after installation**. Confirm only loopback model connections and no
   DNS/remote attempts; confirm no Node/npm/git processes. WFP/firewall logging or
   a per-process packet capture is an alternative if it records denied attempts
   too. Keep captures local and redact them before sharing.
4. In the disposable account, seed global OpenCode config/auth and a project's
   `opencode.json` / `.opencode/opencode.json` with the same fake conflicts used
   by `smoke.py`. Check they remain unchanged, global config/auth are not read,
   and settings resolve only from the private prefix. Do not use a real token.
5. Workspace and server: start the fixture with a tool call, e.g.
   `python -c "import sys; sys.path.insert(0, r'common-mode\tests'); from fake_openai import serve; s = serve(8000, tool_call={'name': 'write', 'arguments': {'filePath': r'C:\ws\result.txt', 'content': 'OK'}}); s.serve_forever()"`.
   Then run `& "$Prefix\bin\ai4science.cmd" --workspace C:\ws run --format json 'Write result.txt.'` and check that
   `C:\ws\result.txt` exists. Also run `serve` with `$env:AI4SCIENCE_SERVER_PASSWORD` and check that it answers 401
   without the password.
6. Confirm no PWM/ledger files, `ai4science.cmd upgrade` returns 2 and the engine
   hash stays unchanged. Verify installed OpenCode/ripgrep/npm license files.
   Repeat existing-prefix refusal and corrupted-archive rejection (Get-FileHash
   verifies the committed SHA). Inspect a failure log without posting credentials.
7. Record OS/CPU, PowerShell version, commands, pin, output, trace summary and all
   failures. Script presence/static review is not a Windows execution result.

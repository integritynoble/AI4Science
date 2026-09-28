# AI4SCI-06 common mode report

Date: 2026-09-28
Branch: `fleet/ai4sci-06-common-mode`
Pin: OpenCode `1.18.33`, latest GitHub release at the time of review.

## Delivered

- Added the isolated `ai4science` wrapper, Linux/macOS and Windows installers, provider defaults, pinned runtime, MIT third-party notice, terms memo, and Windows/macOS test instructions.
- Installers verify the platform package against the npm SHA-512 integrity value. They need network access only for package setup; the user needs neither Git nor Node.
- The wrapper uses AI4Science-specific XDG config, data, state, and cache directories, disables OpenCode auto-update, remote model metadata fetch, default plugins, and LSP downloads, and uses the built-in OpenAI Responses provider pointed by default at `127.0.0.1:8000`. It also primes the provider adapter during installation against a closed loopback port; this downloads provider runtime dependencies from npm before the first session, without contacting a model or sending user data.
- The shipped settings name the provider “AI4Science user OpenAI-compatible endpoint”; OpenCode has no application-name root setting. Plugin and MCP configuration are empty/off.

## Terms summary

The OpenCode source and `opencode-ai` npm package are MIT. Redistribution requires retaining the copyright and permission notices. “Built on OpenCode” is suitable as a factual description with a clear non-affiliation statement; keep OpenCode out of the product name and logo, and do not use its brand art as AI4Science's. Anthropic's consumer terms prohibit automated/non-human use except through an API key or explicit permission, so AI4Science will not support Claude Pro/Max OAuth. OpenAI's consumer terms prohibit automated/programmatic extraction and its documented ChatGPT subscription login is for Codex CLI; AI4Science will not reuse ChatGPT subscription credentials. API keys are separate products. See [TERMS.md](TERMS.md) for source quotes, URLs, read dates, and boundaries requiring owner/counsel review.

## Linux check on abraham

Installed to a temporary prefix using `install.sh` and the downloaded pinned package archive (`AI4SCIENCE_PACKAGE_ARCHIVE` test override). The installer checked the archive integrity, primed the provider, and `ai4science --version` returned `1.18.33`. `debug paths` showed config/data/cache/state under that prefix; `debug config` showed model `openai/local-model`, AI4Science provider label, `plugin: []`, and `mcp: {}`.

Ran `ai4science run --format json 'Say exactly LOCAL_OK'` with the local `fake_openai.py` fixture and a dummy key. It returned `LOCAL_OK`; the fixture received `/v1/responses` requests from `127.0.0.1`. A `strace -f -e trace=connect` capture showed only connections to `127.0.0.1` (the fake server). No PWM ledger or proxy is referenced or enabled by these common-mode files. OpenCode emitted a nonfatal host warning that it could not add an inotify watch on the checkout's `.git` path because the host reported “No space left on device”; the session still completed successfully.

The first fresh-prefix install/priming step may access npm to retrieve the provider runtime dependency. That work is completed before the user's first session and is not model traffic. No credentials were printed; the test used a disposable dummy value.

## Other systems and upstream rehearsal

- `integrity-wsl`: SSH check attempted, but port 22 returned “Connection refused”; the second Linux install/session could not be run.
- Windows and macOS: scripts and written procedures are present in `README.md`; no machine was available for execution.
- Upstream rehearsal: moved from the prior release pin `1.18.32` to `1.18.33`, the release marked latest by GitHub on 2026-09-28. Repeated the abraham temp-prefix install, version check, and fake-server session on `1.18.33`. No wrapper/config change was needed for the update. The tested Linux x64 npm artifact's SHA-512 matches its registry integrity metadata.

## Remaining operational report

`/srv/fleet/bin/process-update` is not installed on this machine (`/srv` contains no fleet directory), so the requested `process-update --log` action could not be run. This report records the result instead. No release, publication, deployment, or push was performed.

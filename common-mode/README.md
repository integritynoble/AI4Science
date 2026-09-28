# AI4Science common mode

AI4Science common mode is a small launcher and isolated configuration around the pinned upstream OpenCode executable. It keeps the upstream MIT notice and makes branding, provider defaults, and optional integrations through OpenCode's supported configuration. OpenCode does not expose an application-name setting in its configuration, so the AI4Science name is used for the command and provider display label. It does not modify OpenCode's source.

This wrapper is easier to audit and update than a fork: upstream fixes arrive by changing one version pin and repeating the compatibility checks. A fork is justified only if a required AI4Science behavior cannot be expressed through stable settings, plugins, MCP, or an external launcher, and upstream cannot accept the capability. Any fork should remain minimal, carry upstream notices, and document its divergence.

The installer downloads the platform-specific binary npm package at the exact version in `VERSION`; the user does not need Git or Node. Network access is required during installation. The installer makes one placeholder model request to a closed loopback port to prime OpenCode's provider adapter from npm (it does not contact a model or send user data). This keeps package registry traffic in setup, before the first user session. The launcher sets private config, auth/data, cache, and state paths under the AI4Science prefix and never reads the user's global OpenCode config or credentials. Set `AI4SCIENCE_OPENAI_BASE_URL` (default `http://127.0.0.1:8000/v1`) and `OPENAI_API_KEY` for the user's own OpenAI-compatible endpoint or a local server; edit `$AI4SCIENCE_PREFIX/config/opencode.json` to choose another provider. Provider metadata fetch, auto-update, default plugins, and LSP downloads are disabled in the wrapper. No AI4Science PWM provider, ledger, proxy, plugin, or MCP server is enabled; `plugin: []` and `mcp: {}` are reserved slots for AI4SCI-07. `AI4SCIENCE_PACKAGE_ARCHIVE` is an optional local `.tgz` override for offline installer tests; ordinary installation downloads the pinned package from npm.

To install on Linux or macOS:

```sh
./install.sh
AI4SCIENCE_PREFIX="$HOME/.local/ai4science" "$HOME/.local/ai4science/bin/ai4science" --version
```

Use the install PowerShell script on Windows, then run `%LOCALAPPDATA%\AI4Science\bin\ai4science.ps1 --version`. The installer places the runtime and wrapper in `%LOCALAPPDATA%\AI4Science`. `AI4SCIENCE_PREFIX` overrides the default prefix on all platforms.

“Built on OpenCode” may be used only as factual descriptive text with a non-affiliation note. OpenCode is not part of the AI4Science product name or logo. See [TERMS.md](TERMS.md) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Platform test procedure

For Linux and macOS, create a temporary prefix, install, and check `--version`. Start `python3 fake_openai.py` (Python 3 is needed only for this test fixture) bound to `127.0.0.1:8000`, set `OPENAI_API_KEY=test`, then run `AI4SCIENCE_PREFIX=<prefix> <prefix>/bin/ai4science run --format json 'Say exactly LOCAL_OK'`. Check that the response contains `LOCAL_OK`, the fixture log contains the `/v1/responses` request, and a connection trace shows only loopback. Repeat on macOS with the arm64 and x64 package as applicable.

For Windows, set `$env:AI4SCIENCE_PREFIX` to a new temporary directory, run `./install.ps1`, then `& "$env:AI4SCIENCE_PREFIX/bin/ai4science.ps1" --version` and the same fake-server session (start server at `127.0.0.1:8000`). Inspect the fake server request log and Windows Resource Monitor or `Get-NetTCPConnection` during the session to confirm only loopback model traffic. No Windows/macOS fleet machine was available for this packet, so these are procedures rather than claimed executions.

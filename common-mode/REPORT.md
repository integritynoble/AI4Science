# AI4SCI-06 common mode — abraham report

Date: 2026-10-02. Host: `abraham`, Linux x86_64 (`7.0.0-31-generic`). Branch:
`fleet/ai4sci-06-common-mode`. Scope: milestones 1–3 on abraham only. No upstream
update rehearsal, integrity-wsl connection, push, release, publication or public
comment was performed. The local commit hash is recorded in the job's `result.md`.

## Delivered

- [TERMS.md](TERMS.md): installed npm and matching source MIT comparison; notice
  requirements; name/logo interpretation; current official Anthropic and OpenAI
  subscription-login policies, short quotations, URLs and read dates. Claude
  subscription login is prohibited for this wrapper. OpenAI documents an
  authorized local open-source flow, but this wrapper's login implementation
  remains off pending eligibility/client/branding review.
- [ai4science](ai4science) / [ai4science.ps1](ai4science.ps1): unmodified pinned
  OpenCode **1.18.34** under our command, version banner and configured research
  agent/username. Its own global config/auth/state/cache are isolated. Only
  `own-llm/local` is enabled; endpoint, API key and actual model ID are supplied
  by the user. PWM MCP is explicitly disabled and the plugin list is empty.
- [install.sh](install.sh) / [install.ps1](install.ps1): native platform artifacts,
  committed engine/search checksums, notices, private defaults, dependency setup
  at install time, runtime offline npm. No user-installed Node/npm/git is needed
  for the supported first-session path. Existing prefixes are never replaced.
- [README.md](README.md): installation/use, boundaries, why a wrapper, conditions
  that could force a fork, and the future PWM extension point.
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md): full upstream MIT notice and
  ripgrep's MIT option; installed search/package notice files are retained.
- [TESTING.md](TESTING.md), fake OpenAI-compatible server and smoke harness:
  repeatable Linux checks plus explicit macOS/Windows procedures.

No upstream engine source was changed. Everything here is a launcher, settings,
installer, test fixture or documentation under `common-mode/`.

## abraham proof

The final installation used the normal npm/GitHub download branches into:
`/home/abraham-yang/qwen-tasks/ai4sci-06-m1/tmp/no-node network install`.
Its installer PATH contained only the documented shell utilities, with **no
Node, npm or git**. Both engine and search-archive checksums passed. OpenCode's
embedded runtime installed the pinned `@opencode-ai/plugin@1.18.34` dependency
with its package manager; the temporary no-op setup plugin was removed.

`ai4science --version` returned:

```text
AI4Science common mode (OpenCode 1.18.34)
```

The Linux harness traced the launcher/engine and children using strace network
and file-open events. It checked version, resolved settings, available models
and a non-interactive JSON session against the local fixture. Default model
`local` and custom ID `science-test-model` both returned `AI4SCIENCE_LOCAL_OK`.
Each session made two chat-completion requests (main response and title helper),
both to the same fake endpoint. The final trace permitted only
`127.0.0.1:45071`.

There were **no DNS or external network attempts**, PWM proxies or ledger files.
The fixture also supplied conflicting global/project config, a fake global OAuth
token and inherited inline/config/database/model/proxy overrides. Resolved settings
ignored those conflicts. Global OpenCode config/auth files were not opened and
all external fixture files remained unchanged. Runtime PATH also excluded Node,
npm and git. Project source files can be indexed as workspace data; that is
separate from loading their settings.

[Machine-readable evidence](evidence/abraham.json) records the exact destinations,
versions, checks and native engine SHA-256. Raw logs, traces and fixture requests
are retained locally under job `tmp/proof-default/`, `tmp/proof-custom/` and
`tmp/proof-reviewed/`; they are not committed. Only fake credentials were used.
The installed npm package's LICENSE matched the pinned GitHub source byte-for-byte.

Negative checks passed: corrupted engine and search archives fail before prefix
creation; an existing prefix is refused; direct upgrade and upgrade with leading
global options return 2. Checks of every installed file confirmed preservation on
existing-prefix/direct-upgrade refusal. Shell syntax, default JSON, lock formats,
staged whitespace and secret-pattern checks passed.

The first-session tracing caught upstream's deferred ripgrep download. Search is
now pinned, verified and installed up front. Config dependencies likewise finish
at install time. The final cold-session trace passed after those changes.

## Limits and remaining work

Windows and macOS scripts received static review only; no execution result is
claimed. integrity-wsl is deferred by this job's scope. Linux arm64 musl is refused
because no matching upstream ripgrep artifact exists. Other listed platforms
still need their written procedure executed.

The engine's own UI/help name and wordmark remain; upstream has no full branding
config. Descriptive “built on OpenCode” attribution is an interpretation, not an
explicit trademark license. Promotional logo use, subscription auth, paid/hosted
ChatGPT-plan eligibility and a complete bundled-dependency notice audit need
owner/counsel review before distribution. On Macs with an OpenCode managed profile,
the wrapper refuses to run to preserve isolation. Private home/managed overrides
use upstream test variables and must be revalidated with any future pin change.

This is config isolation, not a network sandbox for arbitrary tools/plugins or
user-edited settings. The dependency graph is not fully vendored; its resolved
lock is retained per installation. AI4SCI-07 supplies the future paid PWM plugin/MCP;
the owner edition's worker remains a separate dependency. Milestone 6 was skipped.

The brief's `abr-folder/tasks/AI4SCI-06/{goal,plan}.md` files were not available in
this supplied workspace; the job's BRIEF.md and explicit user scope governed work.
The required `/srv/fleet/bin/process-update --log "..."` invocation was attempted
and returned **127: No such file or directory** (`/srv/fleet` is absent). Owner/fleet
must rerun that log command where the fleet installation is available. No substitute
fleet state or success record was fabricated.

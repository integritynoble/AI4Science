# AI4Science Release Channels — Dev → RC → Stable

**Date:** 2026-06-14
**Status:** Design (approved decisions recorded; implementation pending)
**Problem:** Today there is effectively **one** distribution channel — the
`main` branch. `install.sh` falls back to `main`, and `ai4science update`
*always* pulls `archive/refs/heads/main.zip`. So every user runs the
bleeding-edge dev tip, which changes on every commit. With many contributors
about to land work, we need (a) a **stable** version for users, kept apart from
the fast-moving dev line, and (b) a **release-candidate** that managers and
testers can exercise — where **only an explicit approval** lets a candidate
become a release.

---

## Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Stable distribution mechanism | **PyPI (primary) + git `stable` branch (no-account fallback)** |
| 2 | How a commit becomes stable | **Maintainer cuts releases** (contributors land on dev, CI-gated; a human promotes) |
| 3 | How testers receive a candidate | **RC channel** — `vX.Y.Z-rcN` pre-release tags, published to an `rc` channel; testers install the real packaged artifact |
| 4 | How "approved to release" is captured | **GitHub Environment approval** — protected `production` environment with named required reviewers; no stable release without a recorded approval |
| — | Context | **Many contributors** — dev churns fast; CI keeps `main` releasable |

---

## 1. Three channels

```
 main (dev) ──cut RC──► rc (vX.Y.Z-rcN) ──test + approve──► stable (vX.Y.Z) + PyPI
 contributors           managers + testers                  end users
 (CI-gated PRs)         (install real artifact)             (production env approval)
```

| Channel | Git ref | Who installs it | What they get | Install selector |
|---------|---------|-----------------|---------------|------------------|
| **dev** | `main` branch | contributors / the curious | bleeding edge; changes per commit | `AI4SCIENCE_CHANNEL=dev` |
| **rc** | `rc` branch + `vX.Y.Z-rcN` pre-release tags | **managers + testers** | a frozen candidate — the exact bits that will ship | `AI4SCIENCE_CHANNEL=rc` |
| **stable** | `stable` branch + `vX.Y.Z` tags | **end users** | the last *approved* release | default |

Rules:
- **`main`** is the integration branch. All core contributions merge here. CI
  keeps it *intended*-to-be-releasable, but it is never *promised* to users.
- **`rc`** is a **frozen candidate** branch. It is reset to a chosen `main`
  commit at cut time and thereafter receives **only cherry-picked
  release-blocking fixes** — never general dev churn — so testers always
  validate a stable target. Each fix batch produces a new `rcN`.
- **`stable`** is approval-gated and **only ever fast-forwards** to the commit
  that an RC was approved at. It never receives direct commits.
  `archive/refs/heads/stable.zip` therefore always equals the latest approved
  release (the no-PyPI-account install fallback).
- **Tags:** `vX.Y.Z-rcN` are pre-releases (rc channel); `vX.Y.Z` are immutable
  final releases (stable channel + PyPI).

**Key property:** the commit tested as `vX.Y.Z-rcN` and the commit released as
`vX.Y.Z` are the *same tree* — promotion changes only the version string
(`0.6.1rc2` → `0.6.1`), never the code. You ship exactly what was approved.

---

## 2. Two contribution paths (independent — don't block plug-in authors)

A "contributor" means two different things; keep the paths separate.

### 2a. Core contributions — ride the release train
Code changes to the CLI / harness (`ai4science/**`, tests, install scripts).
```
contributor PR ─► main (CI gate: full pytest) ─► RC ─► test+approve ─► stable + PyPI
```
These reach end users only when an RC built from them is approved.

### 2b. Plug-in contributions — do NOT ride the release train
Agent / tool **manifests** (the plug-in system in `PLUGIN_STANDARD.md`) are
pure-data, published to the website gallery
(`physicsworldmodel.org/agents/contribute`) and installed at runtime:
```
contributor uploads manifest ─► gallery ─► any user: `ai4science plugins pull <name>`
```
A plug-in is live the moment it is in the gallery, works against any CLI
channel, and earns PWM independently of the release cadence. This is the
bottleneck-free path most contributors should use.

> The rest of this document concerns path **2a** (the CLI release train).

---

## 3. Version scheme (PEP 440)

`ai4science/__init__.py` is the single source of truth (`__version__`, consumed
by `pyproject.toml`'s dynamic version). One release cycle for `0.6.1`:

| State | Version | Channel | Tag |
|-------|---------|---------|-----|
| Dev on `main` | `0.6.1.dev0` | dev | — |
| Candidate 1 | `0.6.1rc1` | rc | `v0.6.1-rc1` |
| Candidate 2 (after fixes) | `0.6.1rc2` | rc | `v0.6.1-rc2` |
| **Approved release** | `0.6.1` | stable | `v0.6.1` |
| Next dev cycle opens | `0.6.2.dev0` | dev | — |

PEP 440 orders these correctly (verified):
`0.6.0 < 0.6.1.dev0 < 0.6.1rc1 < 0.6.1rc2 < 0.6.1 < 0.6.2.dev0`.
So `pip install --pre` on the rc channel always prefers the newest candidate
over the last final, and a stable upgrade never accidentally pulls an rc.
`ai4science version` shows the marker, so everyone knows their line
(e.g. `ai4science 0.6.1rc2 (rc)`).

---

## 4. The release flow (cut → test → approve → promote)

### 4a. Cut an RC (maintainer; `scripts/cut-rc.sh`)
1. **Pre-flight** — choose the `main` commit; clean tree; remote CI green; full
   local `pytest` passes.
2. **Freeze** — reset the `rc` branch to that commit.
3. **Version** — set `__version__ = X.Y.ZrcN`; commit `rc: vX.Y.Z-rcN`.
4. **Tag & push** — tag `vX.Y.Z-rcN`; push `rc` + tag. This triggers the **rc
   publish** workflow → builds and publishes a **PyPI pre-release** + updates
   `archive/refs/heads/rc.zip`. No approval needed to publish an RC.

### 4b. Test (managers + testers)
Install the candidate exactly as users will:
```bash
AI4SCIENCE_CHANNEL=rc curl -fsSL .../install.sh | bash    # or: ai4science update --rc
```
Exercise it. Testing requires **no special access** — anyone can install the rc
channel. File results as issues / a test checklist.

- **Bug found** → fix lands on `main` (normal CI-gated PR), is cherry-picked onto
  `rc`, and the maintainer cuts `rcN+1` (back to 4a step 3).
- **Looks good** → proceed to approval.

### 4c. Approve & promote (`release.yml`, GitHub Environment-gated)
Promotion is a `workflow_dispatch` run (input: the rc version to promote). The
publish job targets a protected **`production`** environment with **named
required reviewers (the managers)**. The run **pauses** until a reviewer clicks
**Approve** in the Actions UI. Only then does the job:
1. Finalize the version on the rc commit (`X.Y.ZrcN` → `X.Y.Z`); tag `vX.Y.Z`.
2. **Fast-forward `stable`** to that commit; push `stable` + tag.
3. Build + **publish the final to PyPI** (`pip install pwm-ai4science` now serves it).
4. Create a GitHub Release (attach wheel/sdist).
5. Open the next dev cycle: bump `main` to `X.Y.(Z+1).dev0`.

Because the publish is environment-gated, **no stable release can happen without
an approval on record** — auditable and not bypassable by a stray push.

---

## 5. install.sh — channel-aware, default stable

Channel from `--dev` / `--rc` flag or `AI4SCIENCE_CHANNEL` (default `stable`).
`AI4SCIENCE_REF` still overrides everything (explicit escape hatch).

| Channel | Resolution order |
|---------|------------------|
| `stable` (default) | PyPI `pip install pwm-ai4science[claude]` → fallback `... @ .../archive/refs/heads/stable.zip` |
| `rc` | PyPI `pip install --pre pwm-ai4science[claude]` → fallback `rc.zip` |
| `dev` | GitHub `... @ .../archive/refs/heads/main.zip` (today's behavior) |

After install, **record the channel** — write `$AI4SCIENCE_HOME/channel`
(`stable` / `rc` / `dev`). `update` reads it so a user stays on their line.

---

## 6. ai4science update — respect the recorded channel

Today `update` hard-codes the `main` zip. New behavior:

- Read `$AI4SCIENCE_HOME/channel` (default `stable`).
- **stable** → `pip install --upgrade pwm-ai4science[claude]`, fallback `stable.zip`.
- **rc** → `pip install --pre --upgrade pwm-ai4science[claude]`, fallback `rc.zip`.
- **dev** → `main.zip` (current `--force-reinstall --no-cache-dir` path).
- `ai4science update --stable | --rc | --dev` switches channel and rewrites the
  `channel` file. (Lets a tester flip to `rc`, then back to `stable` after release.)

Existing environment detection (venv / pipx / PEP 668 system python) is
preserved; only the *source spec* changes per channel.

---

## 7. CI / GitHub Actions

| Workflow | Trigger | Does | Gate |
|----------|---------|------|------|
| `ci.yml` | PR to `main` | full `pytest` (745 tests) + lint | branch protection blocks merge on red — keeps `main` releasable |
| `rc.yml` | push tag `v*-rc*` (or dispatch) | build + publish **PyPI pre-release**; update `rc` branch | none (RCs publish freely) |
| `release.yml` | `workflow_dispatch` (promote rc) | finalize version, tag `vX.Y.Z`, fast-forward `stable`, **publish final to PyPI**, GitHub Release, open next dev | **`production` environment, required reviewers (managers)** |

Roles:
- **Contributors** — open PRs to `main`.
- **Maintainer** — cuts RCs, dispatches the promote workflow.
- **Approvers (managers)** — named reviewers on the `production` environment;
  their click is the release authorization.
- **Testers** — anyone; just install the `rc` channel.

---

## 8. Channel visibility

- `ai4science version` → `ai4science X.Y.Z (stable)` / `X.Y.ZrcN (rc)` /
  `X.Y.Z.devN (dev)`.
- The chat banner / REPL status shows the channel, so rc/dev users are never
  surprised their CLI changed under them.

---

## Out of scope (YAGNI for now)

- Publishing **dev** builds to PyPI. Dev stays GitHub-only.
- Multiple concurrently-supported stable lines / back-port branches. One
  `stable` line until there's a real need.
- LTS / deprecation policy; beta (`bN`) / alpha (`aN`) tiers beyond `rc`.
- Auto-promotion or scheduled release trains (explicitly rejected).

---

## Implementation surface (for the plan)

| File | Change |
|------|--------|
| `ai4science/__init__.py` | dev/rc/final marker convention |
| `scripts/cut-rc.sh` (new) | §4a freeze `rc`, set rcN, tag, push |
| `install.sh` | `AI4SCIENCE_CHANNEL` (`stable`/`rc`/`dev`) + `--rc`/`--dev`; stable default; write `channel` file; `--pre` for rc |
| `ai4science/commands/update.py` | read channel; stable=PyPI/stable.zip, rc=PyPI --pre/rc.zip, dev=main.zip; `--stable`/`--rc`/`--dev` |
| `ai4science/commands/*version*` | show channel marker |
| `.github/workflows/ci.yml` (new) | PR pytest gate |
| `.github/workflows/rc.yml` (new) | rc tag → PyPI pre-release + `rc` branch |
| `.github/workflows/release.yml` (new) | promote (env-gated) → finalize, tag, fast-forward `stable`, PyPI final, GitHub Release, open next dev |
| GitHub repo settings | `production` environment + required reviewers; branch protection on `main`; PyPI API token secret |
| `docs/` | contributor + release runbook: "core PR → dev; plug-in → gallery; maintainer cuts RC; managers approve in the production environment" |

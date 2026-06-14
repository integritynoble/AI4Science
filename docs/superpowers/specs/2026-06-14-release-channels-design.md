# AI4Science Release Channels — Stable vs Dev

**Date:** 2026-06-14
**Status:** Design (approved decisions recorded; implementation pending)
**Problem:** Today there is effectively **one** distribution channel — the
`main` branch. `install.sh` falls back to `main`, and `ai4science update`
*always* pulls `archive/refs/heads/main.zip`. So every user runs the
bleeding-edge dev tip, which changes on every commit. With many contributors
about to land work, users need a **stable** version to install, kept separate
from the fast-moving **dev** line.

---

## Decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Stable distribution mechanism | **PyPI (primary) + git `stable` branch (no-account fallback)** |
| 2 | How a commit becomes stable | **Maintainer cuts releases** (contributors land on dev, CI-gated; a human promotes) |
| 3 | Context | **Many contributors** — dev churns fast; CI must keep `main` releasable |

---

## 1. Channels, branches, tags

| Channel | Git ref | Who writes it | What users get |
|---------|---------|---------------|----------------|
| **dev** | `main` branch | every contributor (CI-gated PRs) | the bleeding edge; changes per commit |
| **stable** | `stable` branch + `vX.Y.Z` tags | the release cut only (fast-forward) | the last release a maintainer promoted |

Rules:
- **`main`** is the integration branch. All core contributions merge here. It is
  always *intended* to be releasable (CI enforces this) but is never *promised*
  to users.
- **`stable`** is maintainer-controlled and **only ever fast-forwards** to a
  tagged commit on the `main` line. It never receives direct commits or merges.
  `archive/refs/heads/stable.zip` therefore always equals the latest release —
  the no-PyPI-account install fallback.
- **`vX.Y.Z`** tags are immutable release points. They are what gets published to
  PyPI and what users can pin to.

---

## 2. Two contribution paths (important: they are independent)

A "contributor" can mean two very different things. Keep the paths separate so
plug-in authors are never blocked on a CLI release.

### 2a. Core contributions — ride the release train
Code changes to the CLI / harness (`ai4science/**`, tests, install scripts).
```
contributor PR ─► main (CI gate: full pytest must pass) ─► maintainer cuts release ─► stable + PyPI
```
These reach end users **only** when a maintainer next cuts a stable release.

### 2b. Plug-in contributions — do NOT ride the release train
Agent / tool **manifests** (the plug-in system in `PLUGIN_STANDARD.md`). These
are pure-data manifests published to the website gallery
(`physicsworldmodel.org/agents/contribute`) and installed at runtime:
```
contributor uploads manifest ─► website gallery ─► any user: `ai4science plugins pull <name>`
```
A plug-in is live the moment it is in the gallery. It needs **no** CLI release,
works against both stable and dev CLIs, and its author earns PWM from per-agent
pool emission independently of the release cadence. This is the path most
"many contributors" should use; it has no maintainer bottleneck.

> The rest of this document is about path **2a** (the CLI release train).

---

## 3. Version scheme (PEP 440)

`ai4science/__init__.py` holds the single source of truth (`__version__`,
consumed by `pyproject.toml`'s dynamic version).

| State | Example | Meaning |
|-------|---------|---------|
| Stable release | `0.6.0` | a tagged, promoted, PyPI-published version |
| Dev (on `main` between releases) | `0.6.1.dev0` | work toward the next release; not yet promoted |

PEP 440 orders these correctly:
`0.6.0  <  0.6.1.dev0  <  0.6.1`. A dev build is unambiguously *newer than the
last stable* and *older than the next stable*, so `pip` upgrades and version
comparisons behave. `ai4science version` shows the marker, so a user can always
tell which line they are on (e.g. `ai4science 0.6.1.dev0 (dev)`).

---

## 4. The maintainer release cut

A documented checklist backed by a helper script `scripts/release.sh`
(idempotent, refuses to run on a dirty tree or red CI). Cutting `X.Y.Z` from
the current `main`:

1. **Pre-flight** — on `main`, clean working tree, remote CI green for the head
   commit. Run the full suite locally as the final gate (`pytest` → all pass).
2. **Finalize version** — drop the dev marker in `__init__.py`
   (`X.Y.Z.dev0` → `X.Y.Z`); commit `release: vX.Y.Z`.
3. **Tag** — `git tag -a vX.Y.Z -m "vX.Y.Z"`.
4. **Promote `stable`** — fast-forward the `stable` branch to this commit; push
   `stable` and the tag.
5. **Publish to PyPI** — `python -m build` then `twine upload dist/*` (or let the
   tag-push CI workflow do it; see §6). This is what makes
   `pip install pwm-ai4science` serve the new release.
6. **Open the next dev cycle** — bump `main` to `X.Y.(Z+1).dev0`; commit
   `chore: open X.Y.(Z+1) dev cycle`; push `main`.

Only the maintainer running this script moves users forward. Day-to-day
contributor merges to `main` never reach stable users until the next cut.

---

## 5. install.sh — default to stable

Channel is selected by `--dev` flag or `AI4SCIENCE_CHANNEL` (default `stable`).
`AI4SCIENCE_REF` still overrides everything (explicit escape hatch).

| Channel | Resolution order |
|---------|------------------|
| `stable` (default) | 1) PyPI `pip install pwm-ai4science[claude]` (latest release) → 2) fallback `pwm-ai4science[claude] @ .../archive/refs/heads/stable.zip` |
| `dev` | GitHub `.../archive/refs/heads/main.zip` (today's behavior) |

After install, **record the channel** the user chose — write
`$AI4SCIENCE_HOME/channel` (one line: `stable` or `dev`). `update` reads it so a
user stays on the line they installed.

---

## 6. ai4science update — respect the recorded channel

Today `update` hard-codes the `main` zip. New behavior:

- Read `$AI4SCIENCE_HOME/channel` (default `stable` if absent).
- **stable** → `pip install --upgrade pwm-ai4science[claude]`
  (PyPI), fallback to `stable.zip`.
- **dev** → `main.zip` (the current `--force-reinstall --no-cache-dir` path).
- `ai4science update --stable` / `--dev` explicitly switches channel and rewrites
  the recorded `channel` file.

All the existing environment detection (venv / pipx / PEP 668 system python) is
preserved; only the *source spec* changes per channel.

---

## 7. CI gate (the safety net for many contributors)

Because the maintainer's release cut trusts that `main` is releasable, `main`
must stay green:

- **PR workflow** (GitHub Actions, on PR to `main`): run the full `pytest` suite
  (currently 745 tests) + lint. Branch protection blocks merge on failure. This
  is what lets a single maintainer cut releases confidently despite many
  contributors.
- **Release workflow** (on tag push `v*`): build + `twine upload` to PyPI using a
  stored API token, then attach the built wheel/sdist to a GitHub Release. This
  automates §4 step 5 (optional but recommended once PyPI is set up).

---

## 8. Channel visibility (so dev users know)

- `ai4science version` → `ai4science X.Y.Z (stable)` or `X.Y.Z.devN (dev)`.
- The chat banner / REPL status shows the channel, so a dev user is never
  surprised that their CLI changed under them.

---

## Out of scope (YAGNI for now)

- Publishing **dev** builds to PyPI (`--pre`). Dev stays GitHub-only; simpler.
- Multiple concurrently-supported stable lines / back-port branches. One
  `stable` line until there's a real need.
- LTS / deprecation policy.
- Auto-promotion or scheduled release trains (explicitly rejected in §Decisions).

---

## Implementation surface (for the plan)

| File | Change |
|------|--------|
| `ai4science/__init__.py` | dev marker convention (`.devN`) |
| `scripts/release.sh` (new) | the §4 cut procedure |
| `install.sh` | `AI4SCIENCE_CHANNEL`/`--dev`, stable default, write `channel` file |
| `ai4science/commands/update.py` | read channel; stable=PyPI/stable.zip, dev=main.zip; `--stable`/`--dev` |
| `ai4science/commands/*version*` | show channel marker |
| `.github/workflows/ci.yml` (new) | PR pytest gate |
| `.github/workflows/release.yml` (new) | tag → PyPI publish |
| `docs/` | contributor guide: "core PR → dev; plug-in → gallery; releases are cut by maintainers" |

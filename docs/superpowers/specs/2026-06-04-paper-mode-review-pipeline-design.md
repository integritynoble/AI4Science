# Paper Mode — Review Pipeline (Design Spec)

**Date:** 2026-06-04
**Status:** Approved for planning
**Scope:** The peer-review *pipeline* only. PWM charging and aixiv publishing are deliberately deferred to follow-on specs (see "Out of Scope").

---

## 1. Overview

Add a third harness mode, `ai4science chat --mode paper`, alongside `common` and
`research`. The user points it at a paper file they choose (PDF / Markdown /
LaTeX); a deterministic multi-agent panel simulates real conference peer review
and produces a structured **review bundle** (per-reviewer reviews + an
area-chair meta-review + an accept/borderline/reject decision), written to the
workspace as JSON + a rendered Markdown report. The user can then chat about the
result, re-run, or review another paper — because it lives in the REPL.

Two depths:

- **Shallow** (free): one generalist reviewer, no area chair; decision derived
  from that reviewer's rating. This is the no-PWM tier.
- **Deep** (PWM-gated): three reviewers with distinct lenses + an area-chair
  synthesis. Deep reviewers may consult the PWM registry (the research tools) to
  judge novelty against registered principles/solutions. The PWM *charge* is a
  **stubbed seam** in this spec (a `payment_gate` function); the real
  charge-to-5th-wallet lands in the economics spec.

**Chosen approach: C (deterministic core + conversational wrapper).** A
deterministic `paper_review` tool orchestrates the panel in code (reproducible,
testable, guaranteed-structured output for aixiv), and the REPL agent can read
the written bundle and discuss/refine afterward.

**Architecture fit:** reuse the native harness exactly as research mode did.
`build_paper_registry = build_common_registry + paper tools`; a `PAPER_PROMPT`
steers the top-level agent to call `paper_review` on the file the user names.
The raw research browse tools are **not** added to the paper-mode agent's
top-level registry — they are used *internally* by deep reviewer sub-runs only.
Common mode remains excluded from both paper and research tools (moat intact).

---

## 2. Components & Files

### 2.1 `ai4science/harness/paper_load.py` — ingestion
`load_paper(path: Path) -> PaperDoc` where
`PaperDoc(title: str, text: str, source_path: str, fmt: str, truncated: bool)`.

- `.md`/`.markdown`/`.txt`/`.tex` → read UTF-8 text directly.
- `.pdf` → extract text: try the `pdftotext` CLI (poppler) via `subprocess`;
  if absent, try `import pypdf`; if neither is available, raise
  `PaperLoadError` with a clear message ("PDF extraction unavailable — provide
  Markdown/LaTeX or install poppler/pypdf").
- **Title heuristic:** first Markdown `# ` heading → else LaTeX `\title{...}` →
  else first non-empty line → else the filename stem.
- **Truncation:** cap `text` at `MAX_PAPER_CHARS = 120_000`; set
  `truncated=True` and append a marker when cut.
- Unknown extension → treat as text. Missing file → `PaperLoadError`.

### 2.2 `ai4science/harness/paper_bundle.py` — output artifact
Dataclasses + serialization (no orchestration logic):

```
ReviewerScores(soundness:int, contribution:int, presentation:int)   # each 1..4
ReviewerReview(
    persona:str, summary:str, strengths:list[str], weaknesses:list[str],
    questions:list[str], scores:ReviewerScores, rating:int, confidence:int,
    error:str|None=None)                                            # rating 1..10, confidence 1..5
MetaReview(summary:str, key_points:list[str], decision:str,        # decision in {accept,borderline,reject}
    justification:str)
ReviewBundle(
    paper:dict, depth:str, reviews:list[ReviewerReview],
    meta_review:MetaReview|None, decision:str,
    aggregate:dict, model:str, backend:str, created_at:str)
```

- `ReviewBundle.to_json() -> str` and `to_markdown() -> str` (human report:
  paper header, each review, meta-review, boxed decision + aggregate scores).
- `ReviewBundle.write(workspace: Path) -> tuple[Path, Path]` writes
  `<workspace>/.ai4science/reviews/<paper-slug>-<n>.json` and `.md`
  (auto-incrementing `<n>` to avoid clobber). Creates the dir if missing.
- `aggregate` = mean rating, mean per-axis scores, reviewer count, error count.
- `created_at` is an ISO string from `datetime.now()` (normal Python; fine here).

### 2.3 `ai4science/harness/paper_review.py` — the panel orchestrator
Pure-ish functions that reuse the harness adapter + `run_loop`.

```
REVIEWER_PERSONAS = [
  ("novelty",      "novelty & significance",        "<prompt>"),
  ("soundness",    "technical soundness & methodology", "<prompt>"),
  ("clarity",      "clarity & reproducibility",     "<prompt>"),
]
GENERALIST_PERSONA = ("generalist", "overall assessment", "<prompt>")
```

**Structured-output mechanism (capture-tool pattern, like Workflow's
StructuredOutput):** each reviewer sub-run is a bounded `run_loop` given a tiny
registry containing exactly one mutating-free capture tool `submit_review`
whose `parameters` JSON Schema **is** the `ReviewerReview` schema (minus
`persona`/`error`). The reviewer is prompted to finish by calling
`submit_review(...)`; the tool records its args and returns `"recorded"`. We
read the captured args back into a `ReviewerReview`. The area chair uses an
analogous `submit_meta_review` tool whose schema is `MetaReview`.

- `structured_subrun(*, adapter, model, system, user_content, schema, extra_tools=()) -> dict`
  builds `[capture_tool, *extra_tools]` into a Registry, runs `run_loop` with a
  low iteration cap and a no-op gate (sub-runs don't touch the user's fs), and
  returns the captured dict (or raises if the reviewer never submitted).
- `run_panel(*, doc, depth, adapter, model, registry_tools=None, on_event=None) -> ReviewBundle`:
  - **shallow:** one `structured_subrun` with `GENERALIST_PERSONA`, no
    `extra_tools`; `meta_review=None`; `decision` derived from rating
    (`>=7 accept`, `>=5 borderline`, else `reject`).
  - **deep:** three `structured_subrun`s (the three personas), each given
    `extra_tools = registry_tools` (the research browse tools) so reviewers can
    check novelty; then one area-chair `structured_subrun` with
    `submit_meta_review`, prompted over the three reviews; `decision` = the
    meta-review's decision.
  - `on_event(label)` optional progress callback (e.g. "reviewer:novelty done")
    so the tool can stream progress to the REPL.
  - Reviewers run sequentially in v1 (simplicity + deterministic token
    accounting); a `# TODO parallelize` note is acceptable.

**Reviewer error handling:** if a reviewer sub-run fails or never submits, that
reviewer is recorded as `ReviewerReview(persona=..., error="...", <zeros/empties>)`
and the panel continues. The area chair is told which reviewers errored. If
**all** reviewers error, `run_panel` raises `PanelError`.

### 2.4 `ai4science/harness/paper_tools.py` — harness tools for paper mode
`paper_tools(*, brand_provider, research_tools_provider) -> list[Tool]` where
`brand_provider() -> tuple[str, str]` returns the REPL's **live**
`(backend, model)` and `research_tools_provider() -> list[Tool]` returns the
research browse tools. (Late binding is required: `/model` can switch the brand
mid-session — see §2.5 for how the REPL wires the live provider.)

- **`paper_review`** — `parameters`: `{path: str (required), depth: str enum
  [shallow, deep] default shallow}`. `func(workspace, *, path, depth="shallow")`:
  1. `load_paper(workspace/path)` (contained to workspace; reject `..` escapes).
  2. `allowed, reason = payment_gate(depth)`; if deep denied → return a message
     explaining deep needs PWM (future) and that it ran **shallow** instead, then
     continue with `depth="shallow"`.
  3. `backend, model = brand_provider()`; `adapter = adapter_for(backend)`
     (resolved fresh per call so it tracks `/model`). Deep →
     `registry_tools = research_tools_provider()`; shallow → `None`.
  4. `bundle = run_panel(...)`; `json_path, md_path = bundle.write(workspace)`.
  5. Return a compact text summary: decision, aggregate scores, per-reviewer
     ratings, and the two artifact paths. `mutating=False` (writes only under
     `.ai4science/reviews/`, an output dir, not user code).
  - Errors (`PaperLoadError`/`PanelError`/bad path) → `"[paper error] ..."`.
- **`payment_gate(depth: str) -> tuple[bool, str]`** — the stubbed economics
  seam. Shallow → always `(True, "")`. Deep → gated on env
  `AI4SCIENCE_PAPER_DEEP` (default **enabled** in this spec) returning a reason
  when disabled. A module comment states the economics spec replaces this body
  with a real PWM charge to wallet `0xa53F7e7Bc6B0Cc182d048217646082DDB2DacfE3`.

### 2.5 `ai4science/harness/repl.py` — wire the mode
- Add `PAPER_PROMPT` (steer: "You are in paper-review mode. When the user names a
  paper file, call `paper_review` with that path and the requested depth, then
  summarize the decision and key points. Default depth is shallow; use deep only
  when the user asks. Discuss the written report on request.").
- Add `build_paper_registry(*, brand_provider=None, **kw)` = `build_common_registry(**kw)`
  then add the `paper_review` tool built via
  `paper_tools(brand_provider=brand_provider, research_tools_provider=research_tools.research_tools)`.
  (Research browse tools stay OUT of the top-level paper registry; deep reviewers
  receive them internally via the tool.)
- **Live-brand wiring:** the registry-builder call in `_build_session` (currently
  `(registry_builder or build_common_registry)(workspace=…, session_factory=…,
  enable_pwm=…, enable_subagents=…)`) gains one argument:
  `brand_provider=lambda: (active_backend, active_model)`. Because
  `active_backend`/`active_model` are closure locals that `/model` reassigns
  (`session.set_brand(...)` path), the lambda always reports the live brand.
  `build_common_registry` and `build_research_registry` must accept and ignore
  `brand_provider` (add `brand_provider=None` or `**_`) so the shared call site
  stays uniform; only `build_paper_registry` uses it.

### 2.6 `ai4science/commands/chat.py` — route the mode
- Generalize the mode set to `("common", "research", "paper")`; select
  `build_paper_registry` / `PAPER_PROMPT` / `mode_label="paper"`.
- Update the `--mode` help text and the unknown-mode fallback list.

### 2.7 Docs
- `docs/CLAUDE_CODE_PARITY.md`: add a Paper-mode subsection (what it adds, the
  moat note, the deferred economics/aixiv seams).

---

## 3. Data Flow

```
user (in --mode paper, brand chosen): "review ./mypaper.pdf deeply"
  → agent calls paper_review(path="./mypaper.pdf", depth="deep")
    → load_paper → PaperDoc(text, title, …)
    → payment_gate("deep") → allowed
    → run_panel(deep):
        reviewer[novelty]   ─┐  (each: persona prompt + paper text
        reviewer[soundness] ─┤   + research tools; ends by submit_review)
        reviewer[clarity]   ─┘
              → area_chair (sees 3 reviews; submit_meta_review) → decision
    → ReviewBundle.write → reviews/mypaper-1.json + .md
  → tool returns: "Decision: borderline · mean rating 5.7 · …  (wrote …json/.md)"
  → agent narrates; user asks follow-ups (agent reads the bundle)
```

---

## 4. Error Handling (summary)

| Failure | Behavior |
|---|---|
| Paper file missing / path escapes workspace | `[paper error] …`, no panel run |
| PDF extractor unavailable | `PaperLoadError` → `[paper error]` telling user to use MD/LaTeX or install poppler/pypdf |
| One reviewer sub-run fails / never submits | recorded as errored reviewer; panel continues; meta-review notified |
| All reviewers fail | `PanelError` → `[paper error]` |
| Deep requested but `payment_gate` denies | message + automatic shallow fallback |
| Paper longer than `MAX_PAPER_CHARS` | truncated, flagged in bundle + report |

---

## 5. Testing (TDD)

- **paper_load:** MD `#`-title, LaTeX `\title{}`, `.txt`, missing file, unknown
  ext → text, PDF-without-extractor path (monkeypatch subprocess + block pypdf),
  truncation flag.
- **paper_bundle:** `to_json`/`to_markdown` shape; shallow (meta_review None) vs
  deep; `write` returns two paths + auto-increments; aggregate math.
- **paper_review (run_panel) with a STUB adapter** emitting canned
  `submit_review`/`submit_meta_review` tool-calls:
  - deep → 3 reviews + meta + decision == meta decision;
  - shallow → 1 review, derived decision thresholds (rating 8→accept, 6→borderline, 3→reject);
  - a reviewer that never submits → recorded errored, panel continues;
  - all-fail → `PanelError`;
  - deep passes `registry_tools` into reviewer sub-runs; shallow passes none.
- **payment_gate:** shallow always allowed; deep gated by env flag.
- **paper_tools:** `paper_review` end-to-end with stub adapter + tmp workspace →
  returns summary string, writes the two files under `.ai4science/reviews/`; bad
  path → `[paper error]`; deep-denied → shallow-fallback message; `mutating` flag.
- **repl/chat wiring:** `build_paper_registry` includes `paper_review` and does
  **not** include `pwm_solutions`/research browse tools at top level; `chat`
  routes `--mode paper` → harness with `PAPER_PROMPT` + `mode_label="paper"`;
  unknown `--mode` still falls back to common.
- **Moat regression:** common mode registry has neither `paper_review` nor any
  `pwm_*` browse tool.

---

## 6. Out of Scope (explicit — future specs)

- **PWM economics:** the real deep-review charge to wallet `0xa53F…cfE3`,
  balance checks, shallow-vs-deep entitlement. Here it is only the
  `payment_gate` stub.
- **aixiv.physicsworldmodel.org publishing:** selecting "worthy" reviewed papers
  and publishing them. The JSON bundle is designed to be the artifact aixiv will
  later consume, but no publishing happens here.
- **Author-rebuttal round** (considered and declined for v1).
- **Auto-"worthy" threshold logic.**
- **Parallel reviewer execution** (v1 runs reviewers sequentially).

---

## 7. Moat & Consistency Notes

- Paper mode's top-level agent gets `paper_review` but not the raw PWM registry
  browse tools; those reach only deep reviewer sub-runs. Common mode gets
  neither paper nor research tools. Research mode is unchanged.
- Naming follows existing conventions (`build_*_registry`, `*_PROMPT`,
  `paper_*` tools mirroring `pwm_*`).
- Reuses `run_loop`, the adapter factory, `Tool`/`Registry`, persistence, and
  brand-switching with no changes to those modules.

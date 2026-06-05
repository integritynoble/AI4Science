# AI4Science Agent Framework (Design Spec)

**Date:** 2026-06-04
**Status:** Approved for planning
**Relationship:** Foundation for the mode system. Generalizes the existing
`common`/`research` modes and the planned `paper` mode (see
`2026-06-04-paper-mode-review-pipeline-design.md`) into a uniform, plug-and-play
agent framework. **Build this first; refactor research + paper to register as
agents under it.**

---

## 1. Overview

Today the harness has three hard-coded modes (`common`, `research`, `paper`)
wired by three `build_*_registry` functions and routed by an `if mode in (...)`
in `chat.py`. This spec replaces that with a **registry of `AgentSpec`s** that
are auto-discovered from files, so new agents plug in by dropping a file — no
core edits.

**Mode menu becomes:** `/mode` → `common · research · paper · specific ▸ (N)`,
where `specific` is a *category* holding many searchable domain agents
(computational-imaging, biology, chemistry, …).

**Key principles (from the director, 2026-06-04):**

1. **Every agent is full Claude Code first.** Each agent is built on the
   complete Claude-Code base toolset (fs edit, bash, grep, glob, generic
   subagents, MCP) and *adds* its specialization on top. No agent is a narrow
   tool. (Aligns with "Claude Code first; PWM opt-in specialization.")
2. **Two tiers — the moat.** Every agent has a `tier`:
   - **`open`** — only `common`. The generic Claude-Code agent: base toolset
     only, **no PWM tools, no PWM dataset**, and it **cannot dispatch any
     science agent**. Common behaves exactly like Claude Code and is fully
     walled off from the PWM/science world.
   - **`science`** — `research`, `paper`, and every `specific` sub-mode. Full
     Claude-Code base **+** PWM/science capabilities **+ the PWM dataset**.
     **These agents ARE the moat** (the PWM registry/solutions/dataset live
     only behind them). *(This supersedes the earlier "delegation allowed"
     decision of 2026-06-04: common gets no path, direct or indirect.)*
3. **`research`, `paper`, and every `specific` sub-mode are agents** (tier
   `science`); `common` is the lone `open` agent.
4. **Science agents can dispatch agents; common cannot.** When a **science**
   agent runs as the *main* agent it gets the agent-dispatch capability —
   research-as-main can dispatch `paper`, `computational-imaging` can dispatch
   `research`, etc. **Common never gets science-agent dispatch.** Orchestrating
   other agents happens only inside the science (moat) world.
5. **Main-XOR-sub invariant.** Any agent may run as a *sub-agent* of another
   science agent. But an agent **running as a sub-agent may not dispatch
   further agents** — in one process an agent is main XOR sub; named-agent
   nesting depth is exactly 1. (Sub-agents keep fs/bash/etc.; they only lose the
   agent-dispatch capability.) Toggle = `is_subagent`.
6. **The wall is absolute for common — but common still has generic helpers.**
   Common cannot reach the PWM world directly (no PWM tools/dataset) or
   indirectly (no science-agent dispatch); there is no common→science delegation
   path. Common **may** still dispatch **generic/open helper sub-agents** (the
   ordinary Claude-Code `Task` helper — no PWM, no dataset), so it orchestrates
   "just like Claude Code." Two kinds of dispatch target: **open/generic**
   (any main may dispatch) and **science** (only science mains may dispatch).
7. **Plug-and-play.** New agents are declared as auto-discovered manifest files
   and appear under `/mode specific` and as dispatchable sub-agents (of science
   agents).

**Out of scope:** always-alive server agents that are simultaneously main *and*
sub (director's point 4); YAML manifests (Python specs in v1); a large catalog
of domain agents (ship `common`/`research`/`paper` + one example `specific`
agent to prove the path); rich per-domain custom toolsets beyond the optional
`extra_tools` hook.

---

## 2. Components & Files

New package `ai4science/harness/agents/` (distinct from the legacy SDK-era
`ai4science/agents/`, which is unrelated):

### 2.1 `spec.py` — the plug-in unit
```python
@dataclass(frozen=True)
class AgentSpec:
    name: str                       # "common" | "research" | "paper" | "computational-imaging"
    tier: str                       # "open" (no PWM, dispatchable by anyone) | "science" (PWM moat)
    category: str                   # "core" (top-level) | "specific" (under the search list)
    title: str                      # short human label
    description: str                # one-line; shown in /mode + used in dispatch enum
    keywords: tuple[str, ...] = ()  # extra search terms
    system_prompt: str | None = None
    capabilities: tuple[str, ...] = ()   # bundle names ADDED on top of the Claude-Code base
    allow_as_subagent: bool = True
    extra_tools: Callable | None = None  # optional ctx -> list[Tool] for custom domain tools
```
`common` is an `AgentSpec` (`tier="open"`, category `core`, no specialization,
no capabilities). `research`/`paper` are `tier="science"`, category `core`, with
`capabilities=("pwm-actions","pwm-data")` / `("pwm-actions","paper-review")` and
their prompts. The PWM dataset reaches an agent **only** through the
`pwm-data`/`paper-review` bundles, which only science specs list — so `tier`
and `capabilities` together are the moat.

### 2.2 `capabilities.py` — capability bundles
A name → provider map resolving a bundle to tools, given a build context:
```python
CAPABILITY_BUNDLES: dict[str, Callable[[BuildContext], list[Tool]]] = {
    "pwm-actions":  lambda ctx: pwm_action_tools(ctx),   # status/validate/judge/lookup (was in common base)
    "pwm-data":     lambda ctx: research_tools.research_tools(),
    "paper-review": lambda ctx: paper_tools(brand_provider=ctx.brand_provider,
                                             research_tools_provider=research_tools.research_tools),
    # future: "compute", "imaging", "chem", …
}
```
The **Claude-Code base** (fs read/write/edit/grep/glob + MCP, included for every
agent) is *not* a bundle — it is assembled directly (see `build_registry_for`).
**Note the migration:** the PWM *action* tools (`pwm_status`/`pwm_validate`/
`pwm_judge_cassi`/`pwm_lookup_artifact`) move OUT of the common base into the
`pwm-actions` bundle, so `common` no longer carries any `pwm_*` tool. Unknown
capability name → loud error at discovery time (fail fast, listed in tests).

### 2.3 `registry.py` — discovery + lookup + build
- **Discovery:** import every module in `ai4science/harness/agents/specs/` and
  collect each module's top-level `AGENT: AgentSpec` into
  `AGENT_REGISTRY: dict[str, AgentSpec]`. Discovery path is overridable (a
  module-level constant / env) so tests can point at a temp dir.
- **Lookup/search:**
  - `get(name) -> AgentSpec | None`
  - `core_agents() -> list[AgentSpec]` (category `core`)
  - `specific_agents() -> list[AgentSpec]`
  - `search(query) -> list[AgentSpec]` — case-insensitive token/substring match
    over `name + title + description + keywords`, ranked by earliest match
    position; empty query → all specific agents. No new dependency.
- **`build_registry_for(spec, *, is_subagent, ctx) -> Registry`:**
  ```
  reg = _claude_code_base(ctx)                  # pure Claude Code (NO PWM), minus agent-dispatch
  if not is_subagent:
      reg.add(_agent_dispatch_tool(spec, ctx))  # Task over targets spec is cleared for
  for cap in spec.capabilities:
      for t in CAPABILITY_BUNDLES[cap](ctx): reg.add(t)
  if spec.extra_tools:
      for t in spec.extra_tools(ctx): reg.add(t)
  return reg
  ```
  `_claude_code_base(ctx)` = fs read/write/edit/grep/glob + MCP — **no PWM tools
  of any kind** (PWM actions are now the `pwm-actions` bundle). The agent-dispatch
  tool is added only when main (`is_subagent=False`) → enforces the invariant
  (principle 5).

### 2.4 `_agent_dispatch_tool(spec, ctx)` (generalized Task, tier-gated)
Replaces today's `make_task_tool` enum with one driven by the registry **and the
main agent's tier**:
- `subagent_type` enum = `[t.name for t in AGENT_REGISTRY.values()
  if t.allow_as_subagent and _can_dispatch(spec, t)]`, where
  `_can_dispatch(main, target)` = `target.tier == "open"` **or**
  `main.tier == "science"`. So an **open** main (common) sees only open/generic
  targets; a **science** main sees open + science targets. This is principle 4/6.
- On call, builds the child session via the existing `session_factory`, but with
  `registry = build_registry_for(child_spec, is_subagent=True, ctx=child_ctx)`
  and `system_prompt = child_spec.system_prompt`. Returns the child's final
  text. Reuses the existing child-session plumbing (`subagents.py`
  `session_factory`, depth guard) — only the registry/prompt/enum selection changes.
- If the enum would be empty, the dispatch tool is omitted entirely.

### 2.5 `specs/` — the shipped agents (dogfood the framework)
- `specs/common.py` → `tier="open"`, generic Claude-Code agent, no capabilities.
- `specs/general_purpose.py` → `tier="open"`, category `hidden` (a dispatch-only
  agent — NOT listed in the `/mode` menu and not a mode you switch into),
  `allow_as_subagent=True`, no capabilities, no PWM. The generic helper any main
  (incl. common) can dispatch "just like Claude Code." Makes principle 6 concrete.
  (Menu listing keys off `category in ("core","specific")`; `hidden` is skipped.)
- `specs/research.py` → `tier="science"`, `capabilities=("pwm-actions","pwm-data")`,
  holds `RESEARCH_PROMPT`.
- `specs/paper.py` → `tier="science"`, `capabilities=("pwm-actions","paper-review")`,
  holds `PAPER_PROMPT`. (The paper *pipeline* internals — `paper_load`/
  `paper_review`/`paper_bundle`/`paper_tools` — are defined by the paper-mode
  spec; here `paper` is just the spec that wires the `paper-review` bundle.)
- `specs/computational_imaging.py` → **example `specific` science agent** proving
  the plug-in path: `tier="science"`, category `specific`, a domain system
  prompt, `capabilities=("pwm-actions","pwm-data")` (grounds in the CASSI/imaging
  registry), keywords `("cassi","spectral","optics","reconstruction",…)`.

### 2.6 `repl.py` — menu, search, switching
- `/mode` (no arg) → print core agents + `specific ▸ (N) — type /mode specific <query>`.
- `/mode specific [query]` → print `search(query)` results (name — title).
- `/mode <name>` → resolve `get(name)`; if found, switch: rebuild the session
  with that spec's prompt + `build_registry_for(spec, is_subagent=False, ctx)`.
  Reuses the existing rebuild-on-switch path (today's mode toggle), now
  parameterized by `active_spec`.
- The live-brand `brand_provider` (paper mode's seam) is carried on `ctx`.

### 2.7 `commands/chat.py` — routing
- `--mode <name>` resolves against `AGENT_REGISTRY` (default `common`). Unknown →
  print the available agents and fall back to `common`.
- Replace the `if mode in ("common","research","paper")` block with: look up the
  spec, set `system_prompt = spec.system_prompt`, `mode_label = spec.name`, and
  `registry_builder = lambda **kw: build_registry_for(spec, is_subagent=False, ctx=...)`.
- The legacy `_run_chat` SDK path (already dead) is removed in this refactor.

### 2.8 `BuildContext`
A small dataclass threaded into builders/capabilities:
`BuildContext(workspace, brand_provider, session_factory, read_only, auto_yes,
enable_pwm=True, enable_mcp=True)`. Lets capability bundles resolve the live
brand (`paper-review`) and lets the dispatch tool build child sessions.

---

## 3. Data Flow

**Switching mode:**
```
/mode specific imaging
  → registry.search("imaging") → [computational-imaging, …]
/mode computational-imaging
  → spec = get(...) ; session rebuilt with spec.prompt
    + build_registry_for(spec, is_subagent=False, ctx)
    = Claude-Code base + pwm-actions + pwm-data + agent-dispatch(open+science)
```

**Science delegation (main-XOR-sub):**
```
research (science, main) → dispatch subagent_type="paper"
  child = build_registry_for(paper, is_subagent=True, ctx)
        = Claude-Code base + pwm-actions + paper-review, but NO agent-dispatch
  child runs, returns review summary → research
  (child cannot spawn further agents — invariant holds)
```

**Common is walled off:**
```
common (open, main) → dispatch enum = [general-purpose]   # open targets only
  • subagent_type="research" → NOT in enum → [dispatch error]
  • common registry has no pwm_* / paper_review tools, no PWM dataset
common (open, main) → dispatch subagent_type="general-purpose"  # OK, generic helper, no PWM
```

---

## 4. Migration

- `build_common_registry` → splits into `_claude_code_base` (no PWM) + the
  `common` spec. `build_research_registry`/`build_paper_registry` are deleted;
  their behavior is reproduced by `research`/`paper` specs + `build_registry_for`.
  Update all callers (`chat.py`, tests). `RESEARCH_PROMPT`/`PAPER_PROMPT` move
  into the spec files (re-exported from `repl` if tests import them).
- **Behavior change:** common loses the PWM *action* tools it carried before
  (`pwm_status`/`validate`/`judge`/`lookup`) — they move to the `pwm-actions`
  bundle on science specs. Common becomes pure Claude Code. (The 2026-06-02 live
  probe showed common holding those; that is intentionally rolled back here.)
- `research_tools` / `paper_tools` modules are unchanged; referenced by bundles.
- The moat test is **strengthened**: `common`'s built registry has **no `pwm_*`
  tool of any kind** and **no `paper_review`**, and its dispatch enum lists
  **only open targets** (e.g. `general-purpose`) — it does **not** include
  `research`/`paper`/specific (principle 6). A `research` (science) main's enum
  *does* include them.

---

## 5. Error Handling

| Failure | Behavior |
|---|---|
| Spec file with no `AGENT` / duplicate `name` | discovery raises with the offending file (fail fast) |
| `capabilities` names an unknown bundle | discovery raises listing valid bundle names |
| `/mode <name>` unknown | print available agents; stay in current mode |
| `--mode <name>` unknown | print available agents; fall back to `common` |
| dispatch `subagent_type` not in enum / `allow_as_subagent=False` | tool returns `[dispatch error] unknown agent …` |
| sub-agent attempts dispatch | impossible — no dispatch tool in its registry (invariant) |

---

## 6. Testing (TDD)

- **Discovery:** point discovery at a temp dir with a sample `AGENT`; it appears
  in `AGENT_REGISTRY`, `search`, and the dispatch enum. Duplicate name → error.
  Unknown capability → error.
- **`build_registry_for`:** main registry contains the agent-dispatch tool +
  every base tool (fs/bash/grep/glob — "Claude Code first" holds for *every*
  agent); sub registry contains the base tools but **not** agent-dispatch.
  Capability bundles add their tools; `extra_tools` is honored.
- **Invariant:** a spec built with `is_subagent=True` has no dispatch tool →
  named-agent recursion is structurally impossible.
- **Tier gating (`_can_dispatch`):** open main (`common`) → enum excludes every
  `science` agent, includes open targets (`general-purpose`); science main
  (`research`) → enum includes open + science targets.
- **Search:** query filters/ranks; empty query → all specific agents; matches on
  keyword and on title.
- **Menu/switch (repl):** `/mode` lists core + specific count; `/mode specific q`
  lists filtered; `/mode <name>` rebuilds with the right prompt+registry;
  unknown name leaves mode unchanged.
- **chat routing:** `--mode research`/`paper`/`computational-imaging` resolve via
  the registry; unknown falls back to common; `mode_label` == spec name.
- **Moat (the headline test):** `common` built registry has **no `pwm_*` and no
  `paper_review` tool**, and its dispatch enum **excludes** `research`/`paper`/
  specific (only `general-purpose`); a `research`-main can both reach
  `pwm_solutions` directly and dispatch `paper`. A `research` run as a *sub-agent*
  has neither dispatch nor the ability to recurse.
- **Regression:** research mode still answers a `pwm_solutions` query; paper spec
  exposes `paper_review` (pipeline tested in the paper-mode spec).

---

## 7. Sequencing

1. Build the framework: `spec`/`capabilities`/`registry`/dispatch + migrate
   `common` & `research` specs + repl menu/search + chat routing. (Research must
   keep working end-to-end after migration.)
2. Add the example `specific` agent (`computational-imaging`) to prove plug-in.
3. **Then** build the paper-mode pipeline (its own spec) as the `paper-review`
   capability + `paper` spec.
4. Later specs: PWM economics (deep-review charge), aixiv publishing, more
   `specific` domain agents (pure plug-ins now).

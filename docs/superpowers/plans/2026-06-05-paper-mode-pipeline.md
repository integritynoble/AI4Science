# Paper Mode Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `paper` science-tier agent — a deterministic multi-agent peer-review pipeline that reviews a user-chosen paper file (PDF/Markdown/LaTeX), producing reviewer reviews + an area-chair meta-review + an accept/borderline/reject decision, written as a JSON + Markdown bundle — and plug it into the agent framework as the `paper-review` capability.

**Architecture:** Approach C (deterministic core + conversational wrapper). A `paper_review` harness tool orchestrates the panel in code: it loads the paper, runs N reviewer sub-runs (each a bounded `run_loop` that ends by calling a `submit_review` capture tool whose JSON schema IS the review structure), then an area-chair synthesis sub-run, and writes a `ReviewBundle`. It plugs into the framework via a `paper-review` capability bundle + a `paper` `AgentSpec` (tier `science`). The agent (in `--mode paper`) calls `paper_review` and then discusses the written bundle.

**Tech Stack:** Python 3, stdlib only (`dataclasses`, `subprocess`, `json`, `pathlib`, `datetime`), pytest. PDF text via the `pdftotext` CLI (poppler, already installed at `/usr/bin/pdftotext`). No new third-party deps.

**Specs:**
- Pipeline design: `docs/superpowers/specs/2026-06-04-paper-mode-review-pipeline-design.md` (read it). Its §2.5/§2.6 (repl/chat wiring) are **superseded** by the agent framework — paper plugs in as a capability bundle + spec, NOT a `build_paper_registry`.
- Framework: `docs/superpowers/specs/2026-06-04-agent-framework-design.md`.

**Framework integration points (already built):**
- `ai4science/harness/agents/capabilities.py` — `CAPABILITY_BUNDLES: dict[str, Callable[[BuildContext], list[Tool]]]`; the `"paper-review"` key is reserved for this plan. `BuildContext` has `.workspace`, `.brand_provider` (`() -> (backend, model)` live), `.session_factory`.
- `ai4science/harness/agents/spec.py` — `AgentSpec(name, tier, category, title, description, keywords=(), system_prompt=None, capabilities=(), allow_as_subagent=True, extra_tools=None)`.
- `ai4science/harness/agents/specs/*.py` — drop `paper.py` here; auto-discovered.
- `ai4science/harness/agents/registry.py` — `build_registry_for`, `reload`, `core_agents`, `get`.

**Reused harness primitives (confirmed signatures):**
- `ai4science/harness/tools/base.py` — `Tool(name, description, parameters, func, mutating=False)`, `Registry().add(tool)`, `.get(name)`, `.specs()`.
- `ai4science/harness/loop.py` — `run_loop(*, adapter, model, reasoning, history, workspace, registry, gate, on_text, meter) -> str`. It executes tool calls via `tool.func(workspace, **tc.arguments)`.
- `ai4science/harness/permissions.py` — `PermissionGate(*, workspace, read_only, auto_yes, confirm=None)`.
- `ai4science/harness/events.py` — `Message(role, content="", tool_calls=[], tool_call_id=None)`, `ToolCall(id, name, arguments, extra=None)`, `TextDelta(text)`, `Done`.
- `ai4science/harness/adapters/factory.py` — `adapter_for(backend)`, `make_meter(*, backend, model)`.
- `ai4science/harness/research_tools.py` — `research_tools() -> list[Tool]` (deep reviewers' PWM-data tools).

**Run tests:** `PYTHONPATH=$(pwd) python3 -m pytest <path> -v` from `/home/spiritai/pwm/Physics_World_Model/AI4Science` (use `python3`). Baseline on `main`: `381 passed, 4 skipped, 2 failed` — the 2 failures (`tests/test_chat.py::test_list_sessions_*`, `claude_agent_sdk` absent) are pre-existing; leave them.

**Branch:** create `feat/paper-mode` off `main` before Task 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `ai4science/harness/paper_load.py` | Ingest a paper file → `PaperDoc(title, text, source_path, fmt, truncated)` |
| `ai4science/harness/paper_bundle.py` | `ReviewerReview`/`MetaReview`/`ReviewBundle` dataclasses + JSON/Markdown serialization + `write` |
| `ai4science/harness/paper_review.py` | Panel orchestrator: personas, `structured_subrun`, `run_panel(deep/shallow)` |
| `ai4science/harness/paper_tools.py` | `paper_review` Tool + `payment_gate` (PWM-charge stub) |
| `ai4science/harness/agents/capabilities.py` | (modify) register the `paper-review` bundle |
| `ai4science/harness/agents/specs/paper.py` | the `paper` AgentSpec (tier science) + `PAPER_PROMPT` |
| `docs/CLAUDE_CODE_PARITY.md` | (modify) document paper mode |
| `tests/test_harness_paper_*.py` | unit tests per module |

---

## Task 1: `paper_load` — ingest PDF/Markdown/LaTeX

**Files:**
- Create: `ai4science/harness/paper_load.py`
- Test: `tests/test_harness_paper_load.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_paper_load.py
import subprocess
import pytest
from ai4science.harness import paper_load
from ai4science.harness.paper_load import load_paper, PaperDoc, PaperLoadError, MAX_PAPER_CHARS


def test_markdown_title_from_heading(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("# Great Title\n\nAbstract here.\n")
    doc = load_paper(p)
    assert isinstance(doc, PaperDoc)
    assert doc.title == "Great Title"
    assert "Abstract here." in doc.text
    assert doc.fmt == "md"


def test_latex_title(tmp_path):
    p = tmp_path / "a.tex"
    p.write_text(r"\documentclass{article}\title{My Paper}\begin{document}body\end{document}")
    doc = load_paper(p)
    assert doc.title == "My Paper"


def test_txt_title_falls_back_to_first_line(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("First line is the title\nmore text\n")
    doc = load_paper(p)
    assert doc.title == "First line is the title"


def test_missing_file_raises(tmp_path):
    with pytest.raises(PaperLoadError):
        load_paper(tmp_path / "nope.md")


def test_unknown_extension_treated_as_text(tmp_path):
    p = tmp_path / "a.rst"
    p.write_text("Some content\n")
    doc = load_paper(p)
    assert "Some content" in doc.text


def test_truncation_flag(tmp_path):
    p = tmp_path / "big.md"
    p.write_text("# T\n" + ("x" * (MAX_PAPER_CHARS + 100)))
    doc = load_paper(p)
    assert doc.truncated is True
    assert len(doc.text) <= MAX_PAPER_CHARS + 200  # includes the truncation marker


def test_pdf_uses_pdftotext(tmp_path, monkeypatch):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    def fake_run(cmd, **kw):
        class R: returncode = 0; stdout = "# PDF Title\nextracted body"
        return R()
    monkeypatch.setattr(paper_load.subprocess, "run", fake_run)
    monkeypatch.setattr(paper_load.shutil, "which", lambda n: "/usr/bin/pdftotext")
    doc = load_paper(p)
    assert doc.title == "PDF Title" and "extracted body" in doc.text


def test_pdf_without_extractor_raises(tmp_path, monkeypatch):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(paper_load.shutil, "which", lambda n: None)
    monkeypatch.setattr(paper_load, "_pypdf_text", lambda path: None)
    with pytest.raises(PaperLoadError) as e:
        load_paper(p)
    assert "pdftotext" in str(e.value).lower() or "pdf" in str(e.value).lower()
```

- [ ] **Step 2: Run test → FAIL** (`ModuleNotFoundError: ... paper_load`).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_paper_load.py -v`

- [ ] **Step 3: Implement `ai4science/harness/paper_load.py`**

```python
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_PAPER_CHARS = 120_000
_TEXT_EXTS = {".md", ".markdown", ".txt", ".tex"}


class PaperLoadError(Exception):
    pass


@dataclass
class PaperDoc:
    title: str
    text: str
    source_path: str
    fmt: str
    truncated: bool = False


def _pypdf_text(path: Path):
    """Optional fallback if pypdf is installed; returns text or None."""
    try:
        import pypdf
    except Exception:
        return None
    try:
        reader = pypdf.PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return None


def _pdf_text(path: Path) -> str:
    exe = shutil.which("pdftotext")
    if exe:
        try:
            r = subprocess.run([exe, str(path), "-"], capture_output=True,
                               text=True, timeout=120)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout
        except Exception:
            pass
    alt = _pypdf_text(path)
    if alt and alt.strip():
        return alt
    raise PaperLoadError(
        "PDF text extraction unavailable: install poppler (pdftotext) or pypdf, "
        "or provide the paper as Markdown/LaTeX.")


def _guess_title(text: str, fmt: str, fallback: str) -> str:
    if fmt == "tex":
        m = re.search(r"\\title\{([^}]*)\}", text)
        if m and m.group(1).strip():
            return m.group(1).strip()
    for line in text.splitlines():
        s = line.strip()
        if fmt in ("md", "pdf") and s.startswith("# "):
            return s[2:].strip()
        if s:
            return s
    return fallback


def load_paper(path: Path) -> PaperDoc:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise PaperLoadError(f"paper file not found: {path}")
    ext = path.suffix.lower()
    if ext == ".pdf":
        fmt, text = "pdf", _pdf_text(path)
    else:
        fmt = {".md": "md", ".markdown": "md", ".tex": "tex"}.get(ext, "txt")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            raise PaperLoadError(f"could not read {path}: {exc}")
    truncated = False
    if len(text) > MAX_PAPER_CHARS:
        text = text[:MAX_PAPER_CHARS] + "\n\n[...truncated...]"
        truncated = True
    title = _guess_title(text, fmt, path.stem)
    return PaperDoc(title=title, text=text, source_path=str(path), fmt=fmt,
                    truncated=truncated)
```

- [ ] **Step 4: Run test → PASS** (8 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_paper_load.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/paper_load.py tests/test_harness_paper_load.py
git commit -m "feat(paper): paper_load ingests PDF/Markdown/LaTeX"
```

---

## Task 2: `paper_bundle` — the review artifact

**Files:**
- Create: `ai4science/harness/paper_bundle.py`
- Test: `tests/test_harness_paper_bundle.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_paper_bundle.py
import json
from ai4science.harness.paper_bundle import (
    ReviewerScores, ReviewerReview, MetaReview, ReviewBundle, derive_decision)


def _review(persona="novelty", rating=7):
    return ReviewerReview(persona=persona, summary="s", strengths=["a"],
                          weaknesses=["b"], questions=["q"],
                          scores=ReviewerScores(3, 3, 3), rating=rating, confidence=4)


def test_derive_decision_thresholds():
    assert derive_decision(8) == "accept"
    assert derive_decision(6) == "borderline"
    assert derive_decision(3) == "reject"


def test_bundle_json_roundtrips():
    b = ReviewBundle(paper={"title": "T"}, depth="shallow", reviews=[_review()],
                     meta_review=None, decision="accept",
                     aggregate={"mean_rating": 7.0}, model="m", backend="gemini",
                     created_at="2026-06-05T00:00:00")
    data = json.loads(b.to_json())
    assert data["decision"] == "accept"
    assert data["reviews"][0]["persona"] == "novelty"
    assert data["meta_review"] is None


def test_bundle_markdown_contains_decision_and_reviews():
    meta = MetaReview(summary="ms", key_points=["k"], decision="borderline",
                      justification="j")
    b = ReviewBundle(paper={"title": "My Paper"}, depth="deep",
                     reviews=[_review("novelty", 8), _review("soundness", 5)],
                     meta_review=meta, decision="borderline",
                     aggregate={"mean_rating": 6.5}, model="m", backend="gemini",
                     created_at="2026-06-05T00:00:00")
    md = b.to_markdown()
    assert "My Paper" in md and "borderline" in md.lower()
    assert "novelty" in md and "soundness" in md


def test_bundle_write_creates_json_and_md(tmp_path):
    b = ReviewBundle(paper={"title": "T", "source_path": "x/My Paper.md"},
                     depth="shallow", reviews=[_review()], meta_review=None,
                     decision="accept", aggregate={}, model="m", backend="g",
                     created_at="2026-06-05T00:00:00")
    jp, mp = b.write(tmp_path)
    assert jp.exists() and mp.exists()
    assert jp.parent == tmp_path / ".ai4science" / "reviews"
    # second write does not clobber
    jp2, mp2 = b.write(tmp_path)
    assert jp2 != jp
```

- [ ] **Step 2: Run test → FAIL.**

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_paper_bundle.py -v`

- [ ] **Step 3: Implement `ai4science/harness/paper_bundle.py`**

```python
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ReviewerScores:
    soundness: int       # 1..4
    contribution: int    # 1..4
    presentation: int    # 1..4


@dataclass
class ReviewerReview:
    persona: str
    summary: str
    strengths: List[str]
    weaknesses: List[str]
    questions: List[str]
    scores: ReviewerScores
    rating: int          # 1..10
    confidence: int      # 1..5
    error: Optional[str] = None


@dataclass
class MetaReview:
    summary: str
    key_points: List[str]
    decision: str        # accept | borderline | reject
    justification: str


@dataclass
class ReviewBundle:
    paper: Dict
    depth: str
    reviews: List[ReviewerReview]
    meta_review: Optional[MetaReview]
    decision: str
    aggregate: Dict
    model: str
    backend: str
    created_at: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    def to_markdown(self) -> str:
        p = self.paper.get("title", "(untitled)")
        lines = [f"# Review: {p}", "",
                 f"**Decision:** {self.decision}  ·  **Depth:** {self.depth}  "
                 f"·  **Backend:** {self.backend}/{self.model}", ""]
        if self.aggregate:
            lines += [f"**Aggregate:** {json.dumps(self.aggregate)}", ""]
        for r in self.reviews:
            lines += [f"## Reviewer — {r.persona}"]
            if r.error:
                lines += [f"_(errored: {r.error})_", ""]
                continue
            lines += [
                f"_rating {r.rating}/10, confidence {r.confidence}/5 — "
                f"soundness {r.scores.soundness}, contribution "
                f"{r.scores.contribution}, presentation {r.scores.presentation}_",
                "", f"{r.summary}", "",
                "**Strengths:** " + "; ".join(r.strengths),
                "**Weaknesses:** " + "; ".join(r.weaknesses),
                "**Questions:** " + "; ".join(r.questions), ""]
        if self.meta_review:
            m = self.meta_review
            lines += ["## Area Chair — meta-review", "", m.summary, "",
                      "**Key points:** " + "; ".join(m.key_points),
                      f"**Decision:** {m.decision}", "", m.justification, ""]
        return "\n".join(lines)

    def write(self, workspace: Path):
        out = Path(workspace) / ".ai4science" / "reviews"
        out.mkdir(parents=True, exist_ok=True)
        src = self.paper.get("source_path") or self.paper.get("title") or "review"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(str(src)).stem).strip("-") or "review"
        n = 1
        while (out / f"{slug}-{n}.json").exists():
            n += 1
        jp = out / f"{slug}-{n}.json"
        mp = out / f"{slug}-{n}.md"
        jp.write_text(self.to_json(), encoding="utf-8")
        mp.write_text(self.to_markdown(), encoding="utf-8")
        return jp, mp


def derive_decision(rating: float) -> str:
    if rating >= 7:
        return "accept"
    if rating >= 5:
        return "borderline"
    return "reject"
```

- [ ] **Step 4: Run test → PASS** (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/paper_bundle.py tests/test_harness_paper_bundle.py
git commit -m "feat(paper): ReviewBundle dataclasses + JSON/Markdown serialization"
```

---

## Task 3: `paper_review` — the panel orchestrator

**Files:**
- Create: `ai4science/harness/paper_review.py`
- Test: `tests/test_harness_paper_review.py`

**Context:** Each reviewer/area-chair is a bounded `run_loop` given a one-tool registry: a `submit_review`/`submit_meta_review` capture tool whose JSON schema mirrors the dataclass. The reviewer is prompted to finish by calling it; the tool records its kwargs into a holder and returns `"recorded"`. After `run_loop`, we read the holder. The stub adapter in the test emits exactly one such tool call per sub-run then stops.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_paper_review.py
import pytest
from ai4science.harness.events import ToolCall, Done
from ai4science.harness.paper_load import PaperDoc
from ai4science.harness import paper_review
from ai4science.harness.paper_review import run_panel, structured_subrun, PanelError
from ai4science.harness.paper_bundle import ReviewerReview


class StubPanelAdapter:
    """Emits one queued tool-call per sub-run (fresh history), then stops."""
    def __init__(self, queue):
        self._queue = list(queue)   # list of (tool_name, args_dict)

    def stream(self, history, specs, *, model, reasoning):
        has_result = any(getattr(m, "role", None) == "tool" for m in history)
        if not has_result and self._queue:
            name, args = self._queue.pop(0)
            yield ToolCall(id="c0", name=name, arguments=args)
        yield Done()


def _doc():
    return PaperDoc(title="T", text="paper body", source_path="T.md", fmt="md")


def _review_args(rating):
    return {"summary": "s", "strengths": ["a"], "weaknesses": ["b"],
            "questions": ["q"], "scores": {"soundness": 3, "contribution": 3,
            "presentation": 3}, "rating": rating, "confidence": 4}


def _meta_args(decision):
    return {"summary": "ms", "key_points": ["k"], "decision": decision,
            "justification": "j"}


def test_structured_subrun_captures_args(tmp_path):
    adapter = StubPanelAdapter([("submit_review", _review_args(7))])
    out = structured_subrun(adapter=adapter, model="m", system="sys",
                            user_content="rev this", capture_tool="submit_review",
                            schema={"type": "object", "properties": {}},
                            workspace=tmp_path)
    assert out["rating"] == 7


def test_structured_subrun_raises_when_no_submit(tmp_path):
    adapter = StubPanelAdapter([])  # emits nothing
    with pytest.raises(paper_review.SubrunError):
        structured_subrun(adapter=adapter, model="m", system="s", user_content="u",
                          capture_tool="submit_review",
                          schema={"type": "object", "properties": {}},
                          workspace=tmp_path)


def test_run_panel_deep(tmp_path):
    # 3 reviewers + 1 area-chair meta, in order
    adapter = StubPanelAdapter([
        ("submit_review", _review_args(8)),
        ("submit_review", _review_args(6)),
        ("submit_review", _review_args(4)),
        ("submit_meta_review", _meta_args("borderline")),
    ])
    bundle = run_panel(doc=_doc(), depth="deep", adapter=adapter, model="m",
                       backend="gemini", workspace=tmp_path)
    assert len(bundle.reviews) == 3
    assert bundle.meta_review is not None
    assert bundle.decision == "borderline"            # from the meta-review
    assert bundle.aggregate["mean_rating"] == 6.0     # (8+6+4)/3


def test_run_panel_shallow_derives_decision(tmp_path):
    adapter = StubPanelAdapter([("submit_review", _review_args(8))])
    bundle = run_panel(doc=_doc(), depth="shallow", adapter=adapter, model="m",
                       backend="gemini", workspace=tmp_path)
    assert len(bundle.reviews) == 1
    assert bundle.meta_review is None
    assert bundle.decision == "accept"                # rating 8 -> accept


def test_run_panel_marks_errored_reviewer(tmp_path, monkeypatch):
    calls = {"n": 0}
    real = paper_review.structured_subrun
    def flaky(**kw):
        if kw["capture_tool"] == "submit_review":
            calls["n"] += 1
            if calls["n"] == 2:
                raise paper_review.SubrunError("boom")
        return real(**kw)
    adapter = StubPanelAdapter([
        ("submit_review", _review_args(7)),
        ("submit_review", _review_args(7)),  # consumed by reviewer 3 after #2 errors
        ("submit_meta_review", _meta_args("accept")),
    ])
    monkeypatch.setattr(paper_review, "structured_subrun", flaky)
    bundle = run_panel(doc=_doc(), depth="deep", adapter=adapter, model="m",
                       backend="gemini", workspace=tmp_path)
    errored = [r for r in bundle.reviews if r.error]
    assert len(errored) == 1


def test_run_panel_all_fail_raises(tmp_path, monkeypatch):
    def always_fail(**kw):
        raise paper_review.SubrunError("nope")
    monkeypatch.setattr(paper_review, "structured_subrun", always_fail)
    with pytest.raises(PanelError):
        run_panel(doc=_doc(), depth="shallow", adapter=StubPanelAdapter([]),
                  model="m", backend="gemini", workspace=tmp_path)
```

- [ ] **Step 2: Run test → FAIL.**

- [ ] **Step 3: Implement `ai4science/harness/paper_review.py`**

```python
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ai4science.harness.events import Message
from ai4science.harness.loop import run_loop
from ai4science.harness.permissions import PermissionGate
from ai4science.harness.tools.base import Tool, Registry
from ai4science.harness.paper_bundle import (
    ReviewerScores, ReviewerReview, MetaReview, ReviewBundle, derive_decision)
from ai4science.harness.paper_load import PaperDoc


class SubrunError(Exception):
    pass


class PanelError(Exception):
    pass


_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
        "scores": {"type": "object", "properties": {
            "soundness": {"type": "integer"}, "contribution": {"type": "integer"},
            "presentation": {"type": "integer"}}},
        "rating": {"type": "integer"}, "confidence": {"type": "integer"}},
    "required": ["summary", "rating"],
}
_META_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "decision": {"type": "string", "enum": ["accept", "borderline", "reject"]},
        "justification": {"type": "string"}},
    "required": ["summary", "decision"],
}

REVIEWER_PERSONAS = [
    ("novelty", "novelty & significance",
     "You are Reviewer 1, focused on NOVELTY and SIGNIFICANCE. Judge originality "
     "versus prior work and the importance of the contribution."),
    ("soundness", "technical soundness & methodology",
     "You are Reviewer 2, focused on TECHNICAL SOUNDNESS and METHODOLOGY. Scrutinize "
     "the method, assumptions, experiments, and whether claims are supported."),
    ("clarity", "clarity & reproducibility",
     "You are Reviewer 3, focused on CLARITY and REPRODUCIBILITY. Judge writing, "
     "structure, and whether the work could be reproduced."),
]
GENERALIST_PERSONA = ("generalist", "overall assessment",
    "You are a peer reviewer giving a complete overall assessment of the paper.")

_REVIEW_INSTRUCTION = (
    "Read the paper below and write a rigorous conference review. When done, call "
    "the `submit_review` tool with: summary, strengths[], weaknesses[], questions[], "
    "scores{soundness,contribution,presentation} (each 1-4), rating (1-10), "
    "confidence (1-5). You MUST finish by calling submit_review exactly once.")
_META_INSTRUCTION = (
    "You are the Area Chair. Read the paper and the reviewer reviews below, then call "
    "`submit_meta_review` with: summary, key_points[], decision "
    "(accept|borderline|reject), justification. Finish by calling submit_meta_review.")


def _capture_tool(name: str, schema: Dict, holder: Dict) -> Tool:
    def _submit(workspace, **kwargs):
        holder["data"] = kwargs
        return "recorded"
    return Tool(name=name, description=f"Record your structured output via {name}.",
                parameters=schema, func=_submit, mutating=False)


def structured_subrun(*, adapter, model, system, user_content, capture_tool,
                      schema, workspace, extra_tools=None, reasoning="low") -> Dict:
    """Run a bounded sub-agent that must end by calling `capture_tool`. Returns args."""
    holder: Dict = {}
    reg = Registry()
    reg.add(_capture_tool(capture_tool, schema, holder))
    for t in (extra_tools or []):
        reg.add(t)
    history = [Message(role="system", content=system),
               Message(role="user", content=user_content)]
    gate = PermissionGate(workspace=Path(workspace), read_only=False, auto_yes=True)
    run_loop(adapter=adapter, model=model, reasoning=reasoning, history=history,
             workspace=Path(workspace), registry=reg, gate=gate,
             on_text=lambda s: None, meter=lambda u: None)
    if "data" not in holder:
        raise SubrunError(f"sub-agent did not call {capture_tool}")
    return holder["data"]


def _to_reviewer_review(persona: str, args: Dict) -> ReviewerReview:
    sc = args.get("scores") or {}
    return ReviewerReview(
        persona=persona, summary=args.get("summary", ""),
        strengths=list(args.get("strengths", [])),
        weaknesses=list(args.get("weaknesses", [])),
        questions=list(args.get("questions", [])),
        scores=ReviewerScores(int(sc.get("soundness", 0)),
                              int(sc.get("contribution", 0)),
                              int(sc.get("presentation", 0))),
        rating=int(args.get("rating", 0)), confidence=int(args.get("confidence", 0)))


def _errored_review(persona: str, msg: str) -> ReviewerReview:
    return ReviewerReview(persona=persona, summary="", strengths=[], weaknesses=[],
                          questions=[], scores=ReviewerScores(0, 0, 0), rating=0,
                          confidence=0, error=msg)


def _aggregate(reviews: List[ReviewerReview]) -> Dict:
    ok = [r for r in reviews if not r.error]
    if not ok:
        return {"mean_rating": 0.0, "reviewers": len(reviews), "errors": len(reviews)}
    mean = sum(r.rating for r in ok) / len(ok)
    return {"mean_rating": round(mean, 2), "reviewers": len(reviews),
            "errors": len(reviews) - len(ok)}


def run_panel(*, doc: PaperDoc, depth: str, adapter, model: str, backend: str,
              workspace, registry_tools=None, reasoning="low",
              created_at: Optional[str] = None) -> ReviewBundle:
    paper_block = f"TITLE: {doc.title}\n\nPAPER:\n{doc.text}"
    reviews: List[ReviewerReview] = []
    meta: Optional[MetaReview] = None

    if depth == "deep":
        personas = REVIEWER_PERSONAS
        extra = registry_tools or []
    else:
        personas = [GENERALIST_PERSONA]
        extra = []

    for key, _lens, persona_prompt in personas:
        system = f"{persona_prompt}\n\n{_REVIEW_INSTRUCTION}"
        try:
            args = structured_subrun(
                adapter=adapter, model=model, system=system,
                user_content=paper_block, capture_tool="submit_review",
                schema=_REVIEW_SCHEMA, workspace=workspace, extra_tools=extra,
                reasoning=reasoning)
            reviews.append(_to_reviewer_review(key, args))
        except SubrunError as exc:
            reviews.append(_errored_review(key, str(exc)))

    if all(r.error for r in reviews):
        raise PanelError("all reviewers failed")

    if depth == "deep":
        rev_text = "\n\n".join(
            f"[{r.persona}] rating {r.rating}: {r.summary}" for r in reviews if not r.error)
        try:
            margs = structured_subrun(
                adapter=adapter, model=model, system=_META_INSTRUCTION,
                user_content=f"{paper_block}\n\nREVIEWS:\n{rev_text}",
                capture_tool="submit_meta_review", schema=_META_SCHEMA,
                workspace=workspace, reasoning=reasoning)
            meta = MetaReview(summary=margs.get("summary", ""),
                              key_points=list(margs.get("key_points", [])),
                              decision=margs.get("decision", "borderline"),
                              justification=margs.get("justification", ""))
            decision = meta.decision
        except SubrunError:
            decision = derive_decision(_aggregate(reviews)["mean_rating"])
    else:
        decision = derive_decision(reviews[0].rating)

    return ReviewBundle(
        paper={"title": doc.title, "source_path": doc.source_path, "fmt": doc.fmt,
               "truncated": doc.truncated},
        depth=depth, reviews=reviews, meta_review=meta, decision=decision,
        aggregate=_aggregate(reviews), model=model, backend=backend,
        created_at=created_at or datetime.now().isoformat(timespec="seconds"))
```

- [ ] **Step 4: Run test → PASS** (6 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_paper_review.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/paper_review.py tests/test_harness_paper_review.py
git commit -m "feat(paper): panel orchestrator (deep/shallow, capture-tool sub-runs)"
```

---

## Task 4: `paper_tools` — the `paper_review` tool + payment gate

**Files:**
- Create: `ai4science/harness/paper_tools.py`
- Test: `tests/test_harness_paper_tools.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_paper_tools.py
import os
import pytest
from ai4science.harness import paper_tools
from ai4science.harness.paper_tools import paper_tools as build_paper_tools, payment_gate
from ai4science.harness.paper_bundle import (ReviewBundle, ReviewerReview, ReviewerScores)


def _fake_bundle():
    r = ReviewerReview("generalist", "s", ["a"], ["b"], ["q"], ReviewerScores(3, 3, 3), 8, 4)
    return ReviewBundle(paper={"title": "T", "source_path": "T.md"}, depth="shallow",
                        reviews=[r], meta_review=None, decision="accept",
                        aggregate={"mean_rating": 8.0}, model="m", backend="g",
                        created_at="2026-06-05T00:00:00")


def _tools(brand=("gemini", "m")):
    return {t.name: t for t in build_paper_tools(
        brand_provider=lambda: brand,
        research_tools_provider=lambda: [])}


def test_payment_gate_shallow_always_allowed():
    assert payment_gate("shallow")[0] is True


def test_payment_gate_deep_can_be_disabled(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_PAPER_DEEP", "0")
    ok, reason = payment_gate("deep")
    assert ok is False and "pwm" in reason.lower()


def test_paper_review_tool_runs_and_writes(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text("# Paper\nbody")
    captured = {}
    def fake_run_panel(**kw):
        captured.update(kw)
        return _fake_bundle()
    monkeypatch.setattr(paper_tools, "run_panel", fake_run_panel)
    monkeypatch.setattr(paper_tools, "adapter_for", lambda b: object())
    tool = _tools()["paper_review"]
    out = tool.func(tmp_path, path="p.md", depth="shallow")
    assert "accept" in out and "p-1.json" in out
    assert (tmp_path / ".ai4science" / "reviews" / "p-1.json").exists()
    assert captured["depth"] == "shallow"


def test_paper_review_deep_denied_falls_back_to_shallow(tmp_path, monkeypatch):
    (tmp_path / "p.md").write_text("# Paper\nbody")
    monkeypatch.setenv("AI4SCIENCE_PAPER_DEEP", "0")
    seen = {}
    def fake_run_panel(**kw):
        seen["depth"] = kw["depth"]
        return _fake_bundle()
    monkeypatch.setattr(paper_tools, "run_panel", fake_run_panel)
    monkeypatch.setattr(paper_tools, "adapter_for", lambda b: object())
    out = _tools()["paper_review"].func(tmp_path, path="p.md", depth="deep")
    assert seen["depth"] == "shallow"        # fell back
    assert "shallow" in out.lower() or "accept" in out


def test_paper_review_bad_path(tmp_path):
    out = _tools()["paper_review"].func(tmp_path, path="../escape.md", depth="shallow")
    assert "[paper error]" in out


def test_paper_review_tool_is_non_mutating():
    assert _tools()["paper_review"].mutating is False
```

- [ ] **Step 2: Run test → FAIL.**

- [ ] **Step 3: Implement `ai4science/harness/paper_tools.py`**

```python
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List

from ai4science.harness.tools.base import Tool
from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.paper_load import load_paper, PaperLoadError
from ai4science.harness.paper_review import run_panel, PanelError

_WALLET = "0xa53F7e7Bc6B0Cc182d048217646082DDB2DacfE3"


def payment_gate(depth: str):
    """STUB economics seam. Shallow is always free. Deep is gated by env
    AI4SCIENCE_PAPER_DEEP (default enabled). The economics spec replaces this
    body with a real PWM charge to wallet 0xa53F...cfE3."""
    if depth != "deep":
        return True, ""
    if os.environ.get("AI4SCIENCE_PAPER_DEEP", "1") == "0":
        return False, ("deep review requires PWM (charged to the review provider "
                       f"wallet {_WALLET}); running shallow instead")
    return True, ""


def _contained(workspace: Path, rel: str):
    target = (Path(workspace) / rel).resolve()
    try:
        target.relative_to(Path(workspace).resolve())
    except ValueError:
        raise PaperLoadError(f"path escapes the workspace: {rel}")
    return target


def paper_tools(*, brand_provider: Callable[[], tuple],
                research_tools_provider: Callable[[], List[Tool]]) -> List[Tool]:
    def _paper_review(workspace, *, path: str, depth: str = "shallow") -> str:
        try:
            target = _contained(Path(workspace), path)
            doc = load_paper(target)
            note = ""
            allowed, reason = payment_gate(depth)
            if not allowed:
                note = f"[note] {reason}\n"
                depth = "shallow"
            backend, model = brand_provider()
            adapter = adapter_for(backend)
            registry_tools = research_tools_provider() if depth == "deep" else None
            try:
                meter = make_meter(backend=backend, model=model)
            except Exception:
                meter = lambda u: None
            bundle = run_panel(doc=doc, depth=depth, adapter=adapter, model=model,
                               backend=backend, workspace=Path(workspace),
                               registry_tools=registry_tools)
            jp, mp = bundle.write(Path(workspace))
            agg = bundle.aggregate.get("mean_rating", "n/a")
            ratings = ", ".join(f"{r.persona}:{r.rating}" for r in bundle.reviews)
            return (f"{note}Decision: {bundle.decision} · mean rating {agg} · "
                    f"[{ratings}]\nWrote {jp} and {mp}")
        except (PaperLoadError, PanelError) as exc:
            return f"[paper error] {exc}"
        except Exception as exc:
            return f"[paper error] {exc}"

    return [Tool(
        name="paper_review",
        description=("Run a multi-agent peer review of a paper file (PDF/Markdown/"
                     "LaTeX) in the workspace. depth 'shallow' (1 reviewer, free) or "
                     "'deep' (3 reviewers + area chair). Writes a JSON+Markdown "
                     "review bundle and returns the decision."),
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "depth": {"type": "string", "enum": ["shallow", "deep"]}},
            "required": ["path"]},
        func=_paper_review, mutating=False)]
```

NOTE: the test monkeypatches `paper_tools.run_panel` and `paper_tools.adapter_for`, so those MUST be module-level names imported into `paper_tools.py` (they are, per the imports above).

- [ ] **Step 4: Run test → PASS** (6 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_paper_tools.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/paper_tools.py tests/test_harness_paper_tools.py
git commit -m "feat(paper): paper_review tool + payment_gate stub"
```

---

## Task 5: Plug into the framework (`paper-review` bundle + `paper` spec)

**Files:**
- Modify: `ai4science/harness/agents/capabilities.py`
- Create: `ai4science/harness/agents/specs/paper.py`
- Test: `tests/test_harness_paper_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_paper_integration.py
from ai4science.harness.agents import registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for
from ai4science.harness.agents import capabilities


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_paper_review_bundle_registered(tmp_path):
    assert "paper-review" in capabilities.CAPABILITY_BUNDLES
    tools = capabilities.resolve_capability("paper-review", _ctx(tmp_path))
    assert "paper_review" in {t.name for t in tools}


def test_paper_spec_discovered():
    registry.reload()
    paper = registry.get("paper")
    assert paper is not None and paper.tier == "science"
    assert "paper-review" in paper.capabilities


def test_paper_in_core_menu():
    registry.reload()
    assert "paper" in {s.name for s in registry.core_agents()}


def test_paper_agent_has_review_tool_common_does_not(tmp_path):
    registry.reload()
    preg = build_registry_for(registry.get("paper"), is_subagent=False, ctx=_ctx(tmp_path))
    assert "paper_review" in preg.names()
    creg = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    assert "paper_review" not in creg.names()
```

- [ ] **Step 2: Run test → FAIL** (`paper-review` not in bundles / `paper` not discovered).

- [ ] **Step 3a: Register the bundle in `capabilities.py`**

Add a provider function and a dict entry. Insert after `_pwm_data`:

```python
def _paper_review(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.paper_tools import paper_tools
    from ai4science.harness.research_tools import research_tools
    return list(paper_tools(brand_provider=ctx.brand_provider,
                            research_tools_provider=research_tools))
```

And add to the `CAPABILITY_BUNDLES` dict:

```python
    "paper-review": _paper_review,
```

(Remove the stale comment "The paper-review bundle is registered by the paper-mode plan ...".)

- [ ] **Step 3b: Create `ai4science/harness/agents/specs/paper.py`**

```python
from ai4science.harness.agents.spec import AgentSpec

PAPER_PROMPT = (
    "You are AI4Science in PAPER-REVIEW mode. When the user names a paper file "
    "(PDF/Markdown/LaTeX) in the workspace, call the `paper_review` tool with that "
    "path and the requested depth, then summarize the decision and the key points "
    "of the reviews. Default depth is 'shallow' (one reviewer, free); use 'deep' "
    "(three reviewers + area chair) only when the user asks. After the review is "
    "written you can read and discuss the bundle in .ai4science/reviews/."
)

AGENT = AgentSpec(
    name="paper",
    tier="science",
    category="core",
    title="Paper review",
    description="Simulated peer review of a paper file → reviews + decision.",
    keywords=("paper", "review", "peer review", "referee", "manuscript"),
    system_prompt=PAPER_PROMPT,
    capabilities=("pwm-actions", "paper-review"),
)
```

- [ ] **Step 4: Run test → PASS** (4 passed). Also re-run the framework registry tests to confirm no regression:

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_paper_integration.py tests/test_harness_agents_registry.py tests/test_harness_agents_moat.py -v`
Expected: all pass. (`test_menu_partitions_core_vs_specific` still holds — `paper` is core, fine.)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/capabilities.py ai4science/harness/agents/specs/paper.py tests/test_harness_paper_integration.py
git commit -m "feat(paper): register paper-review capability + paper AgentSpec (tier science)"
```

---

## Task 6: Full suite, live E2E, docs

**Files:**
- Modify: `docs/CLAUDE_CODE_PARITY.md`

- [ ] **Step 1: Full suite**

Run: `PYTHONPATH=$(pwd) python3 -m pytest -q`
Expected: all green except the 2 pre-existing `test_list_sessions_*` failures. Fix any new red from the integration before continuing.

- [ ] **Step 2: Live E2E (controller-run; the implementer SKIPS network)**

```bash
# Menu shows paper as a core mode:
WS=$(mktemp -d); printf '/mode\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode common --workspace "$WS" 2>&1 | tail -8
# Expect: the menu lists common / research / paper.

# A real shallow review on Gemini:
WS2=$(mktemp -d)
printf '# Toward Faster CASSI Reconstruction\n\nWe propose a lightweight unrolled network for snapshot compressive spectral imaging that halves inference time while matching MST-L PSNR. Experiments on the standard 10-scene benchmark show 34.9 dB at 12ms.\n' > "$WS2/paper.md"
printf '/model gemini gemini-3.1-pro-preview\nReview ./paper.md (shallow).\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode paper --workspace "$WS2" 2>&1 | tail -20
# Expect: the agent calls paper_review(path="paper.md", depth="shallow"); a decision
# (accept/borderline/reject) is printed; .ai4science/reviews/paper-1.json + .md exist.
ls -la "$WS2/.ai4science/reviews/" 2>&1
```

- [ ] **Step 3: Update `docs/CLAUDE_CODE_PARITY.md`**

READ the file, then under the "Agent framework" section append a short "Paper mode" note: `--mode paper` is a science-tier agent exposing `paper_review` (deep = 3 reviewers + area chair, shallow = 1 reviewer); it writes a JSON+Markdown bundle to `.ai4science/reviews/`; deep reviewers may consult the PWM registry; the PWM charge is a stubbed `payment_gate` (env `AI4SCIENCE_PAPER_DEEP`); the bundle is the artifact a future aixiv site will consume. Keep it ~8 lines, matching the doc tone.

- [ ] **Step 4: Commit**

```bash
git add docs/CLAUDE_CODE_PARITY.md
git commit -m "docs(paper): document paper mode in CLAUDE_CODE_PARITY"
```

---

## After all tasks

1. Dispatch a final whole-implementation reviewer over `main..feat/paper-mode`.
2. Controller runs the Step 2 live E2E and captures output (the real review bundle).
3. Use `superpowers:finishing-a-development-branch` → merge to `main` locally.
4. Update memory `project_paper_mode.md` → built & merged.
5. Follow-on specs/plans: PWM economics (real deep-review charge), aixiv publishing.

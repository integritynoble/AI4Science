"""Retrieval baseline — lexical + task-scoped retrieval with optional semantic arm.

Provides a unified `retrieve()` call that the working-memory gate can use to
select relevant semantic entries and episodes before assembling W_t.

Two modes (selected by the SARSI_SEMANTIC_RETRIEVAL env var):
  lexical (default, mode A): task/scope filter + keyword overlap scoring.
  semantic (mode B): same as lexical plus TF-IDF-style token intersection boost.

Mode B is only enabled when SARSI_SEMANTIC_RETRIEVAL=1.  The gate uses lexical
by default; semantic must improve Recall@k on the frozen benchmark by a
pre-declared amount before being set as the default.

Invariants:
  - Protected entries (scope=global, kind=invariant/causal_rule) are ALWAYS
    returned regardless of relevance score.  A constraint has no vocabulary in
    common with the task it constrains — a ranked retriever will push it out of
    context exactly when it matters most.
  - Superseded semantic entries are NOT returned (active_entries() enforces this).
  - The result set is capped at k entries unless the caller raises it.
  - Retrieval failures never raise — callers get an empty result.

Benchmark: run `pytest tests/sarsi/test_retrieval_benchmark.py -v` to measure
Recall@k and protected-directive miss rate against the frozen test cases.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

from ai4science.harness.agents.sarsi import semantic as _sem
from ai4science.harness.agents.sarsi.registry import Agent, Config

#: Default number of non-protected entries to return.
DEFAULT_K = 10

#: Entry kinds that are always returned regardless of relevance (protected arm).
PROTECTED_KINDS = frozenset(("invariant", "causal_rule"))

#: Words ignored during keyword overlap scoring.
_STOPWORDS = frozenset(
    ("the", "a", "an", "is", "in", "to", "and", "of", "for", "it",
     "this", "that", "with", "are", "was", "be", "at", "on", "by",
     "from", "or", "not", "do", "does", "did", "has", "have", "had",
     "its", "as", "so", "but", "if", "we", "you", "they", "he", "she")
)

#: Feature-flag env var name.
_ENV_FLAG = "SARSI_SEMANTIC_RETRIEVAL"


def _semantic_mode() -> bool:
    """True when mode B (semantic arm) is requested via env var."""
    return os.environ.get(_ENV_FLAG, "0").strip() == "1"


def _tokens(text: str) -> set:
    """Tokenise to lowercase words, stripping stopwords and short tokens."""
    words = set(re.findall(r"[a-z]{3,}", text.lower()))
    return words - _STOPWORDS


def _lexical_score(entry: Dict[str, Any], query_tokens: set,
                   task_id: str) -> int:
    """Score by task-id match and keyword overlap with the query."""
    score = 0
    # Task scope match is a strong signal — same-task entries are highly relevant.
    scopes = entry.get("scope") or []
    if task_id and f"task:{task_id}" in scopes:
        score += 4
    # Keyword overlap with query.
    stmt = (entry.get("statement") or entry.get("summary") or "")
    entry_tokens = _tokens(stmt)
    overlap = len(query_tokens & entry_tokens)
    score += min(overlap, 4)
    return score


def _semantic_score(entry: Dict[str, Any], query_tokens: set,
                    task_id: str) -> float:
    """Mode B: lexical score + TF-IDF-style token intersection boost.

    Uses relative overlap (Jaccard) rather than raw count, so short entries
    with high overlap beat long entries with incidental matches.
    """
    base = _lexical_score(entry, query_tokens, task_id)
    stmt = (entry.get("statement") or entry.get("summary") or "")
    entry_tokens = _tokens(stmt)
    if entry_tokens:
        jaccard = len(query_tokens & entry_tokens) / len(query_tokens | entry_tokens)
        return base + jaccard * 2
    return float(base)


def retrieve(config: Config, agent: Agent,
             query: str = "", task_id: str = "",
             scope: Optional[List[str]] = None,
             k: int = DEFAULT_K) -> Dict[str, List[Dict[str, Any]]]:
    """Return relevant semantic memory entries for context injection.

    Returns:
        {
          "protected": [...],   # always included regardless of score
          "retrieved": [...],   # top-k relevant entries
          "mode": "lexical"|"semantic",
        }

    Protected entries are those with kind in PROTECTED_KINDS.  They are
    returned separately so the caller can inject them unconditionally before
    the retrieved slice (the gate ordering per BrainRSI §5.2).
    """
    try:
        scope_filter = list(scope) if scope else None
        all_active = _sem.active_entries(config, agent, scope_filter)
    except Exception as e:
        # An empty result and a broken store are different facts, and the
        # caller has to be able to tell them apart: a turn that lost every
        # constraint to a corrupt store must not look like a turn that had
        # none. The gate records `error` in the manifest. [§11.3(e)]
        return {"protected": [], "retrieved": [], "mode": "lexical",
                "error": f"{type(e).__name__}: {e}"}

    mode = "semantic" if _semantic_mode() else "lexical"
    query_tokens = _tokens(query or "")

    protected: List[Dict[str, Any]] = []
    candidates: List[Dict[str, Any]] = []

    for entry in all_active:
        kind = entry.get("kind", "")
        if kind in PROTECTED_KINDS:
            protected.append(entry)
        else:
            candidates.append(entry)

    # Score and rank candidates.
    if mode == "semantic":
        scored = sorted(candidates,
                        key=lambda e: _semantic_score(e, query_tokens, task_id),
                        reverse=True)
    else:
        scored = sorted(candidates,
                        key=lambda e: _lexical_score(e, query_tokens, task_id),
                        reverse=True)

    return {
        "protected": protected,
        "retrieved": scored[:k],
        "mode": mode,
    }


def render(config: Config, agent: Agent,
           query: str = "", task_id: str = "",
           scope: Optional[List[str]] = None,
           k: int = DEFAULT_K) -> str:
    """Format retrieved entries for context injection.

    Protected entries are labelled as constraints; retrieved entries follow.
    Returns empty string when nothing is available.
    """
    try:
        result = retrieve(config, agent, query=query, task_id=task_id,
                          scope=scope, k=k)
    except Exception:
        return ""

    lines: List[str] = []
    if result["protected"]:
        lines.append("constraints (always active):")
        for e in result["protected"]:
            stmt = (e.get("statement") or "").strip()
            scope_str = ", ".join(e.get("scope") or [])
            lines.append(f"  [constraint] ({scope_str}) {stmt}")
    if result["retrieved"]:
        lines.append(f"retrieved knowledge ({result['mode']} mode, top {k}):")
        for e in result["retrieved"]:
            stmt = (e.get("statement") or "").strip()
            kind = e.get("kind", "")
            scope_str = ", ".join(e.get("scope") or [])
            lines.append(f"  [{kind}] ({scope_str}) {stmt}")

    return "\n".join(lines) if lines else ""

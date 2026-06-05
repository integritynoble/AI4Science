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

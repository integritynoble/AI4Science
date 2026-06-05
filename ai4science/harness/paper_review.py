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

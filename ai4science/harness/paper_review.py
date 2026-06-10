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

# ── Venue profiles (directive 2026-06-10): simulate the review culture and
# acceptance bar of the major journals and conferences. `kind` drives the
# decision vocabulary (journal: editor + revisions; conference: area chair).
VENUE_PROFILES = {
    "nature": ("journal", "Nature",
        "Bar: a major conceptual advance of broad interest to ALL scientists, "
        "not just the subfield; airtight evidence; ~8% acceptance. Editors "
        "desk-reject most papers; referees demand extraordinary support for "
        "extraordinary claims."),
    "science": ("journal", "Science",
        "Bar: a landmark result that changes how the field thinks; broad "
        "general-reader significance; rigorous, complete evidence."),
    "cell": ("journal", "Cell",
        "Bar: a deep mechanistic biological advance with definitive, "
        "multi-angle experimental support; conceptual novelty in biology."),
    "nature-communications": ("journal", "Nature Communications",
        "Bar: a solid, important advance for the specific field — rigor and "
        "completeness matter more than universal appeal."),
    "nature-methods": ("journal", "Nature Methods",
        "Bar: a method the community will adopt — validated against the state "
        "of the art, with usable code/protocols and demonstrated robustness."),
    "prl": ("journal", "Physical Review Letters",
        "Bar: a significant, broadly interesting physics result presentable in "
        "4 pages; correctness and importance over completeness."),
    "pnas": ("journal", "PNAS",
        "Bar: an important multi-disciplinary advance with solid evidence."),
    "nature-machine-intelligence": ("journal", "Nature Machine Intelligence",
        "Bar: a significant ML/AI advance with demonstrated scientific or "
        "societal impact — rigorous benchmarks, strong baselines, and "
        "transparent limitations; broad interest to the AI community."),
    "nature-physics": ("journal", "Nature Physics",
        "Bar: a conceptually important physics advance of interest across "
        "physics; decisive evidence and clear physical insight."),
    "nature-photonics": ("journal", "Nature Photonics",
        "Bar: a major optics/photonics advance — new physics or a capability "
        "leap (imaging, sources, detectors) with rigorous characterization."),
    "nature-materials": ("journal", "Nature Materials",
        "Bar: a landmark materials advance with mechanistic understanding and "
        "robust, reproducible synthesis/characterization."),
    "nature-medicine": ("journal", "Nature Medicine",
        "Bar: a clinically meaningful advance — strong human/translational "
        "evidence, rigorous statistics, clear path to impact on patients."),
    "nature-biotechnology": ("journal", "Nature Biotechnology",
        "Bar: an enabling biotechnological capability with head-to-head "
        "benchmarking and demonstrated real-world utility."),
    "nature-neuroscience": ("journal", "Nature Neuroscience",
        "Bar: a major mechanistic or conceptual neuroscience advance with "
        "convergent evidence across approaches."),
    "nature-electronics": ("journal", "Nature Electronics",
        "Bar: a significant device/system electronics advance with rigorous "
        "performance benchmarking against the state of the art."),
    "nature-computational-science": ("journal", "Nature Computational Science",
        "Bar: a computational method or insight of broad scientific value — "
        "rigorous validation, scalability evidence, open code expected."),
    "scientific-reports": ("journal", "Scientific Reports",
        "Bar: technically sound and original — significance/novelty are NOT "
        "criteria; judge correctness, clarity, and completeness only."),
    "nejm": ("journal", "NEJM",
        "Bar: practice-changing clinical evidence — typically rigorous "
        "randomized trials; statistics and patient outcomes are decisive."),
    "lancet": ("journal", "The Lancet",
        "Bar: clinically important, methodologically rigorous studies with "
        "global health relevance."),
    "jama": ("journal", "JAMA",
        "Bar: rigorous clinical research with direct relevance to medical "
        "practice and policy; statistical review is strict."),
    "elife": ("journal", "eLife",
        "Bar: solid, significant life-science work; constructive consolidated "
        "reviews focused on whether claims are supported."),
    "prx": ("journal", "Physical Review X",
        "Bar: first-rate physics of broad interest with lasting value; "
        "selective but completeness-friendly (no length pressure)."),
    "tpami": ("journal", "IEEE TPAMI",
        "Bar: a mature, thorough vision/ML contribution — comprehensive "
        "experiments, comparisons, and analysis beyond a conference paper."),
    "tip": ("journal", "IEEE TIP",
        "Bar: a solid image-processing advance with thorough quantitative "
        "evaluation against current methods."),
    "tmi": ("journal", "IEEE TMI",
        "Bar: a medical-imaging methodology advance with clinically relevant "
        "validation on real data."),
    "optica": ("journal", "Optica",
        "Bar: a high-impact optics result — significant capability or insight "
        "with rigorous experimental support."),
    "light-science-applications": ("journal", "Light: Science & Applications",
        "Bar: a major photonics/optics advance with strong application "
        "potential and thorough validation."),
    "jacs": ("journal", "JACS",
        "Bar: an important chemistry advance with complete characterization "
        "and mechanistic support."),
    "advanced-materials": ("journal", "Advanced Materials",
        "Bar: high-impact materials science with strong performance metrics "
        "and application relevance."),
    "cvpr": ("conference", "CVPR",
        "Bar: novel vision method + convincing experiments — strong baselines, "
        "SOTA tables, ablations, ideally code. Reviewers are adversarial about "
        "missing comparisons; ~25% acceptance."),
    "iccv": ("conference", "ICCV",
        "Bar: like CVPR — novelty + rigorous vision experiments + ablations."),
    "eccv": ("conference", "ECCV",
        "Bar: like CVPR — novelty + rigorous vision experiments + ablations."),
    "neurips": ("conference", "NeurIPS",
        "Bar: significant ML contribution — theory or strong empirics; clarity "
        "of claims and evidence; reproducibility checklist culture."),
    "icml": ("conference", "ICML",
        "Bar: rigorous ML methodology — proofs or thorough experiments; "
        "precise claims."),
    "iclr": ("conference", "ICLR",
        "Bar: novel learning-representation ideas; open-review culture — "
        "expect direct, public scrutiny of claims."),
    "miccai": ("conference", "MICCAI",
        "Bar: medical-imaging methodology with clinical relevance and sound "
        "validation on real datasets."),
    "siggraph": ("conference", "SIGGRAPH",
        "Bar: striking, technically deep graphics/visual-computing results "
        "with flawless execution and visuals."),
}


def resolve_venue(name):
    """(kind, title, culture) or None. Accepts 'Nature', 'nature comms', etc."""
    if not name:
        return None
    key = str(name).strip().lower().replace(" ", "-").replace("_", "-")
    aliases = {"nature-comms": "nature-communications",
               "ncomms": "nature-communications", "nat-comm": "nature-communications",
               "nature-com": "nature-communications",
               "nmi": "nature-machine-intelligence",
               "nat-mach-intell": "nature-machine-intelligence",
               "nature-mi": "nature-machine-intelligence",
               "pami": "tpami", "t-pami": "tpami",
               "lsa": "light-science-applications",
               "light": "light-science-applications",
               "sci-rep": "scientific-reports", "srep": "scientific-reports",
               "the-lancet": "lancet",
               "nat-comp-sci": "nature-computational-science"}
    key = aliases.get(key, key)
    return VENUE_PROFILES.get(key)


_JOURNAL_META_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "decision": {"type": "string",
                     "enum": ["accept", "minor_revision", "major_revision", "reject"]},
        "justification": {"type": "string"}},
    "required": ["summary", "decision"],
}

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
              created_at: Optional[str] = None,
              venue: Optional[str] = None) -> ReviewBundle:
    paper_block = f"TITLE: {doc.title}\n\nPAPER:\n{doc.text}"
    vprof = resolve_venue(venue)
    venue_label = None
    venue_prefix = ""
    meta_instruction = _META_INSTRUCTION
    meta_schema = _META_SCHEMA
    if vprof:
        vkind, vtitle, vculture = vprof
        venue_label = vtitle
        venue_prefix = (f"This is a submission to **{vtitle}** ({vkind}). Review it "
                        f"BY {vtitle}'S STANDARDS. {vculture}\n\n")
        if vkind == "journal":
            meta_schema = _JOURNAL_META_SCHEMA
            meta_instruction = (
                f"You are the handling EDITOR at {vtitle}. {vculture} Read the paper "
                "and the referee reports below, then call `submit_meta_review` with: "
                "summary, key_points[], decision "
                "(accept|minor_revision|major_revision|reject), justification. "
                "Finish by calling submit_meta_review.")
        else:
            meta_instruction = (
                f"You are the Area Chair for {vtitle}. {vculture} Read the paper and "
                "the reviewer reviews below, then call `submit_meta_review` with: "
                "summary, key_points[], decision (accept|borderline|reject), "
                "justification. Finish by calling submit_meta_review.")
    reviews: List[ReviewerReview] = []
    meta: Optional[MetaReview] = None

    if depth == "deep":
        personas = REVIEWER_PERSONAS
        extra = registry_tools or []
    else:
        personas = [GENERALIST_PERSONA]
        extra = []

    for key, _lens, persona_prompt in personas:
        system = f"{venue_prefix}{persona_prompt}\n\n{_REVIEW_INSTRUCTION}"
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
                adapter=adapter, model=model, system=meta_instruction,
                user_content=f"{paper_block}\n\nREVIEWS:\n{rev_text}",
                capture_tool="submit_meta_review", schema=meta_schema,
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
        created_at=created_at or datetime.now().isoformat(timespec="seconds"),
        venue=venue_label)

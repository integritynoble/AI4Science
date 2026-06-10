from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List

from ai4science.harness.tools.base import Tool
from ai4science.harness.adapters.factory import adapter_for
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
    def _paper_review(workspace, *, path: str, depth: str = "shallow",
                  venue: str = "") -> str:
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
            bundle = run_panel(doc=doc, depth=depth, adapter=adapter, model=model,
                               backend=backend, workspace=Path(workspace),
                               registry_tools=registry_tools, venue=venue)
            # Ensure slug is derived from the actual input file, not bundle metadata
            try:
                rel = target.relative_to(Path(workspace).resolve())
            except ValueError:
                rel = Path(target.name)
            bundle.paper["source_path"] = str(rel)
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
                     "'deep' (3 reviewers + area chair/editor). Optional venue "
                     "simulates a target journal/conference's standards — 29 "
                     "journals (nature, science, cell, nature-communications, "
                     "nature-machine-intelligence, nature-photonics, "
                     "nature-medicine, nejm, lancet, tpami, tip, tmi, optica, "
                     "prx, scientific-reports, …) and 8 conferences (cvpr, iccv, "
                     "eccv, neurips, icml, iclr, miccai, siggraph). "
                     "Journals decide accept/minor_revision/major_revision/reject. "
                     "Writes a JSON+Markdown review bundle and returns the decision."),
        parameters={"type": "object", "properties": {
            "path": {"type": "string"},
            "depth": {"type": "string", "enum": ["shallow", "deep"]},
            "venue": {"type": "string"}},
            "required": ["path"]},
        func=_paper_review, mutating=False)]

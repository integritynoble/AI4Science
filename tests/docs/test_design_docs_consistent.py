"""The three design sources agree, and this is what stops them drifting.

Fourteen disagreements were found by hand on 2026-08-06, between documents that
each looked fine on their own. The expensive one: the record linked a section of
`computational-imaging.md` that had been dropped from the copy the link resolved
to, so a reader following it found a page that simply did not contain what the
record said it did.

A checker nobody runs is a comment. These call it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import check_design_docs as chk  # noqa: E402

SINGULARITY = Path("/home/spiritai/pwm/singularity-docs")


def test_every_documented_agent_has_a_scope_and_a_roster_object():
    """§13j and §13f: an agent whose boundary is prose is one whose boundary
    cannot be violated, because there is nothing to violate."""
    pages = chk.agent_pages(chk.RA)
    assert pages, "no agent pages found at all"
    scope = {p.stem for p in (chk.RA / "scope").glob("*.json")}
    roster = {p.stem for p in (chk.RA / "roster").glob("*.json")}
    assert pages <= scope, "no scope object: %s" % sorted(pages - scope)
    assert pages <= roster, "no roster object: %s" % sorted(pages - roster)


def test_every_implemented_agent_has_a_page():
    from ai4science.harness.agents import research_agents as ra
    code = {chk.ALIAS.get(n, n) for n in ra.NAMES}
    pages = chk.agent_pages(chk.RA)
    assert code <= pages, "implemented but undocumented: %s" % sorted(code - pages)


def test_a_page_with_no_implementation_says_so_in_its_own_words():
    """The check with teeth. Seven of these pages describe agents that read real
    corpora; one describes an agent that does not exist yet. A reader must be
    able to tell them apart from the page, not from the roster."""
    from ai4science.harness.agents import research_agents as ra
    code = {chk.ALIAS.get(n, n) for n in ra.NAMES}
    for name in sorted(chk.agent_pages(chk.RA) - code):
        text = (chk.RA / (name + ".md")).read_text().lower()
        assert any(s in text for s in chk.SAYS_UNBUILT), (
            "%s has no implementation and its page does not say so" % name)


def test_the_alias_between_code_and_docs_is_declared_not_discovered():
    """`imaging` is the code's name for `computational-imaging`, for a reason
    registry.py records. An alias with a stated reason is history; the same
    alias undeclared is one field with two names."""
    from ai4science.harness.agents import research_agents as ra
    src = (REPO / "ai4science/harness/agents/research_agents/registry.py").read_text()
    for code_name, doc_name in chk.ALIAS.items():
        assert code_name in ra.NAMES, "%s is aliased and does not exist" % code_name
        assert code_name in src


@pytest.mark.skipif(not SINGULARITY.exists(), reason="no singularity checkout")
def test_there_is_one_tree_and_the_other_place_only_points_at_it():
    """It was two trees. They forked in both directions, were converged by hand,
    and then diverged again *within minutes* because two sessions were editing
    them. Syncing two copies is not a mechanism, it is a habit — and a habit is
    what stops holding on the day it matters."""
    spec = SINGULARITY / "docs/specs/research-agents"
    strays = sorted(p.name for p in spec.glob("*.md") if p.name != "README.md")
    assert not strays, ("a second copy is not a spare, it is a coin to flip: %s"
                        % strays)
    for sub in ("scope", "roster"):
        assert (chk.RA / sub).is_dir(), "%s objects must live beside the pages" % sub
        assert not (spec / sub).exists(), "%s objects duplicated in the specs tree" % sub


@pytest.mark.skipif(not SINGULARITY.exists(), reason="no singularity checkout")
def test_and_the_pointer_says_where_the_pages_went():
    """A stub that does not name its replacement is worse than no stub: it tells
    a reader the thing is gone and not where to look."""
    spec = SINGULARITY / "docs/specs/research-agents/README.md"
    assert "AI4Science/docs/research-agents" in spec.read_text()


def test_the_pages_outbound_links_resolve_from_where_the_pages_actually_are():
    """The class that actually broke. Every page linked `../2026-08-04-*.md` —
    filenames that exist in the specs tree, from a directory that is not it. The
    links resolved in the copy and not in the original, so following one from
    the canonical page gave nothing."""
    import re
    bad = []
    for page in sorted(chk.RA.glob("*.md")):
        for link in sorted(set(re.findall(r"\]\((\.\./[^)#]+)\)", page.read_text()))):
            if not (page.parent / link).exists():
                bad.append("%s -> %s" % (page.name, link))
    assert not bad, "a link is a claim that the target says something:\n" + "\n".join(bad)


def test_the_scope_objects_still_validate_where_they_now_live():
    """Moving them moved their validator and schema too, or the move quietly
    turned a checked directory into an unchecked one."""
    assert (chk.RA / "scope/validate.py").exists()
    assert (chk.RA / "agent-manifest.schema.json").exists()
    import subprocess, sys as _s
    out = subprocess.run([_s.executable, "scope/validate.py"], cwd=str(chk.RA),
                         capture_output=True, text=True)
    assert "valid" in out.stdout, out.stdout[-800:] + out.stderr[-800:]


@pytest.mark.skipif(not SINGULARITY.exists(), reason="no singularity checkout")
def test_the_record_and_its_mirror_agree_where_they_overlap():
    mirror = (SINGULARITY / "docs/specs/2026-08-04-ai4science-one-machine-design.md")
    rec, mir = chk.RECORD.read_text(), mirror.read_text()
    for start, end in (("## 11. The market", "## 11a."),
                       ("## 11b. Research agents", "## 12. Self-awareness"),
                       ("## 13. What runs it costs", "## 14. What this does not do")):
        def cut(t):
            i = t.find(start)
            assert i >= 0, "%r missing" % start
            return t[i:t.find(end, i)]
        assert cut(rec) == cut(mir), "%s has drifted between the two copies" % start


@pytest.mark.skipif(not SINGULARITY.exists(), reason="no singularity checkout")
def test_every_link_into_research_agents_resolves():
    """The one that was actually broken: a link is a claim that the target says
    something, and it survives the target being rewritten."""
    import re
    spec = SINGULARITY / "docs/specs"
    for path, base in ((chk.RECORD, chk.RA.parent),
                       (spec / "2026-08-04-ai4science-one-machine-design.md", spec),
                       (spec / "2026-08-04-sarsi-agent-market-and-pwm-design.md", spec)):
        if not path.exists():
            continue
        for link in set(re.findall(r"\]\((research-agents/[^)#]+)\)", path.read_text())):
            assert (base / link).exists(), "%s links to a missing %s" % (path.name, link)


def _queue_rows(text):
    """Yield (rung, state) for each row of a page's problem queue table."""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = line.split("|")
        if len(parts) < 6:
            continue
        cells = parts[1:-1]
        if len(cells) != 5 or not cells[0].strip().isdigit():
            continue
        yield cells[0].strip(), cells[-1].strip()


def test_a_rung_marked_done_does_not_report_missing_its_own_bar():
    """A rung's state cell is the page's own claim about itself. A cell that
    says `done` and in the same breath reports clearing the rung's bar on a
    minority of the declared seeds is a page contradicting itself in one cell,
    and the reader has no way to know which half to believe."""
    import re
    for stem in sorted(chk.agent_pages(chk.RA)):
        text = (chk.RA / (stem + ".md")).read_text()
        for rung, state in _queue_rows(text):
            if not state.lower().replace("*", "").startswith("done"):
                continue
            for hits, total in re.findall(r"on (\d+) of (?:the )?(\d+)",
                                          state):
                assert 2 * int(hits) > int(total), (
                    "%s rung %s is marked done and its own cell says it "
                    "clears on %s of %s" % (stem, rung, hits, total))


def test_drug_design_states_its_held_out_number_where_it_states_ef():
    """The field's two one-line claims — its row in the research-agents
    README index, and the `L4 · solution` row of its own page — are where a
    reader who reads nothing else meets this field's result. Both state EF@1%
    and neither states the held-out-target figure, so the number the field's
    own ladder calls the useful one is absent from every summary of it."""
    import re
    readme = (chk.RA / "README.md").read_text()
    page = (chk.RA / "drug-design.md").read_text()
    claims = [ln for ln in readme.splitlines()
              if ln.startswith("| [drug design]") and "EF@1%" in ln]
    claims += [ln for ln in page.splitlines() if "**L4 · solution**" in ln]
    assert len(claims) == 2, (
        "expected exactly the README index row and the L4 · solution row; "
        "if these two rows have been renamed this check has stopped "
        "checking anything and must be re-pointed rather than left to "
        "pass: %s" % (claims,))
    for line in claims:
        assert "EF@1%" in line, line
        where = ("the README index row"
                 if line.startswith("| [drug design]")
                 else "drug-design.md's L4 · solution row")
        assert re.search(r"held[- ]out[- ]target", line, re.I), (
            "%s states EF@1%% and not the held-out-target figure: %s"
            % (where, line[:90]))

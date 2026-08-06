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
    if not SINGULARITY.exists():
        pytest.skip("scope and roster objects live in the singularity checkout")
    spec = SINGULARITY / "docs/specs/research-agents"
    scope = {p.stem for p in (spec / "scope").glob("*.json")}
    roster = {p.stem for p in (spec / "roster").glob("*.json")}
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
def test_there_is_one_copy_of_each_agent_page_not_two_that_disagree():
    spec = SINGULARITY / "docs/specs/research-agents"
    bad = []
    for p in sorted(chk.RA.glob("*.md")):
        q = spec / p.name
        if not q.exists():
            bad.append("%s missing from the specs tree" % p.name)
        elif p.read_text() != q.read_text():
            bad.append("%s differs (%d vs %d lines)"
                       % (p.name, len(p.read_text().splitlines()),
                          len(q.read_text().splitlines())))
    assert not bad, "one of each pair is stale and a reader cannot tell which:\n" + "\n".join(bad)


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

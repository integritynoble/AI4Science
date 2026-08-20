"""Research agents are one-per-FIELD group agents, not one-per-person.

The owner's correction: each agent under ``docs/research-agents/`` is a
**group** — one agent per *field*, internally a set of member roles (reasoning /
judging / embodied) that presents outward as one thing: one workspace, one task
list, one ceiling, one verdict. It is emphatically **not** one agent per person.

The code already keeps this — ``ResearchAgent`` carries a ``charter`` naming a
*field*, never a person, and each agent reaches the sarsi roster as a single
worker id. This file does not fix a bug; it pins the property that is true today
so it cannot regress in silence. The mutation anchor is assertion 3: thread a
``person`` / ``user`` / ``owner_id`` field into ``ResearchAgent`` and this file
turns red.

**What this file asserts and what it leaves elsewhere.** The group's *membership*
— the literature / twin / corpus / method / runner / verifier / reproducer /
teacher / writer members — and the rule that **"the group's ceiling is the lowest
of its members'"** are now built (``ResearchAgent.group``), and are pinned in
``tests/test_research_group_ceiling.py``, the test that fails the day membership
regresses and passes for the right reason. This file keeps its own subject: the
group presents *outward as one agent* — one charter naming a field, one roster
entry, no per-person identity. Assertion 3 below now expects ``group`` in the
field set as the inward half of that property; the embodied rows in
``docs/research-agents/cancer.md`` remain design only, as that page states.
"""
import dataclasses
import os
import subprocess
import sys

import pytest

from ai4science.harness.agents.research_agents import registry as ra

#: Documented, and for a stated reason: the imaging field's charter is named
#: ``imaging`` inside research_agents (it had a runner before that package
#: existed) but reaches the roster as ``computational-imaging``. This is the same
#: alias ``tools/check_design_docs.py`` declares — an alias with a reason is a
#: fact about history, not a second name for the field.
ALIAS = {"imaging": "computational-imaging"}

#: The fields that bound a research agent. Not a person among them. ``group`` is
#: the inward half of the group-agent property this file pins: the agent still
#: presents outward as one thing, but now carries the reasoning/judging members
#: (and the ceiling rule they impose) explicitly. Added deliberately here, in the
#: same commit that built it — not slipped past assertion 3.
EXPECTED_FIELDS = {"charter", "self_model", "switch", "night", "field_map",
                   "group"}


def test_one_entry_per_field_keyed_by_charter_name():
    """Assertion 1. Every key is its charter's name — a field, not a person.

    No duplicate keys, and no per-person suffixing: a key carrying ``@``, ``:``
    or an underscore-separated person part would be the shape of one-agent-per-
    person, which the registry does not have.
    """
    agents = ra.build_all()

    assert list(agents) == list(ra.NAMES)
    assert len(ra.NAMES) == len(set(ra.NAMES)), "duplicate research-agent names"

    for key, agent in agents.items():
        assert key == agent.charter.name, (key, agent.charter.name)
        assert "@" not in key, f"{key!r} carries a per-person '@' part"
        assert ":" not in key, f"{key!r} carries a per-person ':' part"
        assert "_" not in key, f"{key!r} carries an underscore-separated part"


def test_each_agent_describes_a_field_not_a_person_or_project():
    """Assertion 2. A non-empty field, and more than one subfield.

    A single subfield would be a project; a field spans several. A person or a
    project would not have a subfield tuple at all.
    """
    for name, agent in ra.build_all().items():
        ch = agent.charter
        assert ch.field, f"{name}: empty charter.field"
        assert isinstance(ch.subfields, tuple), f"{name}: subfields not a tuple"
        assert len(ch.subfields) > 1, (
            f"{name}: {len(ch.subfields)} subfield(s) — a field has more than "
            "one; a project would not"
        )


def test_no_per_person_identity_is_modelled():
    """Assertion 3 — the mutation anchor.

    ``ResearchAgent``'s annotated fields are exactly the five that bound a field
    agent. If anyone threads a ``person`` / ``user`` / ``owner_id`` field in, this
    set changes and the assertion goes red — which is the point: per-person
    identity has no place on this dataclass.
    """
    annotated = {f.name for f in dataclasses.fields(ra.ResearchAgent)}
    assert annotated == EXPECTED_FIELDS, (
        f"ResearchAgent fields are {sorted(annotated)}, expected "
        f"{sorted(EXPECTED_FIELDS)} — a new field here (person? user? owner_id?) "
        "means per-person identity is being modelled; re-decide the group-agent "
        "property, do not relax this assertion"
    )


def _init(state):
    """A sarsi roster in an isolated state dir. Skips if it cannot be built here.

    Same idiom as ``tests/test_repl_entering_costs_nothing.py::_init``.
    """
    env = {**os.environ, "SARSI_STATE_DIR": str(state), "COLUMNS": "140",
           "TERM": "dumb"}
    init = subprocess.run([sys.executable, "-m", "ai4science.cli", "sarsi",
                           "init", "--owner-id", "7007143162"],
                          capture_output=True, text=True, env=env, timeout=120)
    if init.returncode != 0:
        pytest.skip("cannot init a sarsi registry in this environment: "
                    + (init.stderr or init.stdout)[-400:])
    return env


def _roster_hits(agent_ids, name):
    """Roster ids that are this field's agent, person-suffix and all.

    A per-person expansion would show up here as ``field@alice``, ``field@bob``
    — several hits for one field. A field agent shows up as exactly one, and
    that one carries no suffix.
    """
    hits = []
    for aid in agent_ids:
        base = aid.split("@")[0].split(":")[0]
        if base == name:
            hits.append(aid)
    return hits


def test_outward_it_is_one_agent(tmp_path):
    """Assertion 4. Each wired research agent is exactly one roster entry.

    Built against the real roster in an isolated ``SARSI_STATE_DIR``. For every
    research agent whose (aliased) name reaches the roster, exactly one entry
    matches it, and that entry carries no per-person suffix — outward, the group
    is one agent with one roster listing.
    """
    state = tmp_path / "state"
    _init(state)

    os.environ["SARSI_STATE_DIR"] = str(state)
    from ai4science.harness.agents.sarsi import registry as reg
    config = reg.load(reg.config_path(state))
    agent_ids = list(config.agents)

    wired = 0
    for name in ra.NAMES:
        roster_name = ALIAS.get(name, name)
        hits = _roster_hits(agent_ids, roster_name)
        if not hits:
            continue
        wired += 1
        assert hits == [roster_name], (
            f"{name} (roster {roster_name!r}) matches {hits} — a field agent is "
            "one roster entry with no per-person suffix, not one entry per person"
        )

    assert wired, (
        "no research agent reached the roster — the roster ids are "
        f"{sorted(agent_ids)}; this test would otherwise pass vacuously"
    )

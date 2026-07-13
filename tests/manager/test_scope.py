from ai4science.harness.agents.manager.scope import scope_score, route
from ai4science.harness.agents.spec import AgentSpec

# Minimal stand-in specs (vocabulary mirrors the shipped agents) so the router
# test is deterministic and independent of the live registry.
SPECS = [
    AgentSpec(name="work", tier="open", category="core", title="General Work",
              description="coding data analysis files", keywords=("coding", "data", "analysis", "files")),
    AgentSpec(name="imaging", tier="science", category="specific", title="Computational Imaging",
              description="cassi reconstruction optics", keywords=("cassi", "reconstruction", "optics")),
    AgentSpec(name="learning", tier="open", category="core", title="Personal Learning",
              description="study guide quiz tutor", keywords=("learning", "quiz", "study", "tutor")),
    AgentSpec(name="process-learning", tier="open", category="core", title="Work-Process Learning",
              description="explain trace tutorial postmortem", keywords=("trace", "process", "postmortem")),
    AgentSpec(name="research2", tier="science", category="core", title="Research",
              description="grounded synthesis citations sources", keywords=("research", "citations", "sources")),
]


def _primary(intent, **kw):
    return route(intent, SPECS, **kw)["primary"]


def test_routes_to_correct_agent():
    assert _primary("reconstruct the cassi scene with optics") == "imaging"
    assert _primary("make a study guide and a quiz to tutor me") == "learning"
    assert _primary("do some coding and data analysis on these files") == "work"
    assert _primary("explain the agent trace as a postmortem") == "process-learning"
    assert _primary("research this with citations from the sources") == "research2"


def test_out_of_domain_is_a_gap():
    r = route("book me a flight to paris tomorrow", SPECS)
    assert r["primary"] is None and r["gap"] and "niche agent" in r["gap"]


def test_prefer_boosts():
    # "data" alone matches work; prefer=research2 boosts research2 to the top
    r = route("some data", SPECS, prefer="research2")
    assert r["primary"] == "research2"


def test_scope_score_zero_on_no_overlap():
    s = next(x for x in SPECS if x.name == "imaging")
    assert scope_score(s, "book a flight to paris") == 0.0
    assert scope_score(s, "") == 0.0


def test_ranked_is_sorted_desc():
    r = route("cassi reconstruction study quiz", SPECS)
    scores = [sc for _, sc in r["ranked"]]
    assert scores == sorted(scores, reverse=True)

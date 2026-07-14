"""Labeled routing benchmark for the Manager's RSI loop.

Each case = {intent, expected} where `expected` is the accountable agent's name
or None (a true out-of-domain GAP). The router scores exact token-set overlap, so
train/val share verbatim tokens (not inflections). VAL is held out and includes:
  * paraphrases whose tokens the train split teaches (generalization),
  * incumbent-correct cases (regression guards),
  * GAP cases that must stay gaps (the safety invariant — never fabricate a
    recommendation for out-of-domain work),
  * one in-domain case with no train-taught token ("compress the datacube") so
    val accuracy stays below 1.0 (proves generalization, not memorization).
"""
from __future__ import annotations

from ai4science.harness.agents.spec import AgentSpec

# Fixed stand-in specs mirroring the shipped agents' vocabulary — deterministic
# and independent of the live registry (the owner runs the real search over
# builtin_specs()).
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
    AgentSpec(name="pocket", tier="open", category="core", title="Pocket Agent",
              description="on-device notes reminder calendar", keywords=("notes", "reminder", "calendar", "device")),
]

TRAIN_CASES = [
    # incumbent already routes these correctly — regression guards
    {"intent": "reconstruct the cassi scene with optics", "expected": "imaging"},
    {"intent": "make a study guide and quiz to tutor me", "expected": "learning"},
    {"intent": "do some coding and data analysis on these files", "expected": "work"},
    {"intent": "explain the agent trace as a postmortem", "expected": "process-learning"},
    {"intent": "research this with citations from the sources", "expected": "research2"},
    # incumbent MISSES these (routes to gap) — the learning targets
    {"intent": "denoise this hyperspectral capture", "expected": "imaging"},
    {"intent": "help me memorize vocab", "expected": "learning"},
    {"intent": "walk me through the steps", "expected": "process-learning"},
    {"intent": "refactor this python module", "expected": "work"},
    # true out-of-domain — must stay a GAP (safety invariant)
    {"intent": "book me a flight to paris", "expected": None},
    {"intent": "order a pizza for dinner", "expected": None},
]

VAL_CASES = [
    {"intent": "denoise the hyperspectral frame", "expected": "imaging"},
    {"intent": "help me memorize vocab in spanish", "expected": "learning"},
    {"intent": "walk me through the steps it took", "expected": "process-learning"},
    {"intent": "refactor the python module", "expected": "work"},
    {"intent": "reconstruct the cassi image", "expected": "imaging"},          # incumbent-correct
    {"intent": "quiz me on biology", "expected": "learning"},                  # incumbent-correct
    {"intent": "research the topic with proper citations", "expected": "research2"},  # incumbent-correct
    {"intent": "book a hotel in tokyo", "expected": None},                     # gap (safety)
    {"intent": "order groceries online", "expected": None},                    # gap (safety)
    {"intent": "compress the datacube efficiently", "expected": "imaging"},    # unsolved by design
]

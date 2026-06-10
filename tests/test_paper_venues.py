"""Venue-aware paper review (directive 2026-06-10)."""
from ai4science.harness.paper_review import (VENUE_PROFILES, resolve_venue,
                                             _JOURNAL_META_SCHEMA)


def test_famous_venues_present():
    for v in ("nature", "science", "cell", "nature-communications",
              "nature-machine-intelligence", "nature-photonics",
              "nature-medicine", "scientific-reports", "nejm", "lancet",
              "tpami", "tip", "tmi", "optica", "prx",
              "cvpr", "eccv", "iccv", "neurips", "icml", "iclr"):
        assert v in VENUE_PROFILES, v


def test_resolve_aliases_and_case():
    assert resolve_venue("Nature")[1] == "Nature"
    assert resolve_venue("nature comms")[1] == "Nature Communications"
    assert resolve_venue("NMI")[1] == "Nature Machine Intelligence"
    assert resolve_venue("Nature Machine Intelligence")[1] == "Nature Machine Intelligence"
    assert resolve_venue("PAMI")[1] == "IEEE TPAMI"
    assert resolve_venue("CVPR")[0] == "conference"
    assert resolve_venue("cell")[0] == "journal"
    assert resolve_venue("") is None and resolve_venue("unknown-venue") is None


def test_journal_decision_vocabulary():
    enum = _JOURNAL_META_SCHEMA["properties"]["decision"]["enum"]
    assert enum == ["accept", "minor_revision", "major_revision", "reject"]

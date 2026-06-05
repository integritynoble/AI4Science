import json
from ai4science.harness.paper_bundle import (
    ReviewerScores, ReviewerReview, MetaReview, ReviewBundle, derive_decision)


def _review(persona="novelty", rating=7):
    return ReviewerReview(persona=persona, summary="s", strengths=["a"],
                          weaknesses=["b"], questions=["q"],
                          scores=ReviewerScores(3, 3, 3), rating=rating, confidence=4)


def test_derive_decision_thresholds():
    assert derive_decision(8) == "accept"
    assert derive_decision(6) == "borderline"
    assert derive_decision(3) == "reject"


def test_bundle_json_roundtrips():
    b = ReviewBundle(paper={"title": "T"}, depth="shallow", reviews=[_review()],
                     meta_review=None, decision="accept",
                     aggregate={"mean_rating": 7.0}, model="m", backend="gemini",
                     created_at="2026-06-05T00:00:00")
    data = json.loads(b.to_json())
    assert data["decision"] == "accept"
    assert data["reviews"][0]["persona"] == "novelty"
    assert data["meta_review"] is None


def test_bundle_markdown_contains_decision_and_reviews():
    meta = MetaReview(summary="ms", key_points=["k"], decision="borderline",
                      justification="j")
    b = ReviewBundle(paper={"title": "My Paper"}, depth="deep",
                     reviews=[_review("novelty", 8), _review("soundness", 5)],
                     meta_review=meta, decision="borderline",
                     aggregate={"mean_rating": 6.5}, model="m", backend="gemini",
                     created_at="2026-06-05T00:00:00")
    md = b.to_markdown()
    assert "My Paper" in md and "borderline" in md.lower()
    assert "novelty" in md and "soundness" in md


def test_bundle_write_creates_json_and_md(tmp_path):
    b = ReviewBundle(paper={"title": "T", "source_path": "x/My Paper.md"},
                     depth="shallow", reviews=[_review()], meta_review=None,
                     decision="accept", aggregate={}, model="m", backend="g",
                     created_at="2026-06-05T00:00:00")
    jp, mp = b.write(tmp_path)
    assert jp.exists() and mp.exists()
    assert jp.parent == tmp_path / ".ai4science" / "reviews"
    jp2, mp2 = b.write(tmp_path)
    assert jp2 != jp

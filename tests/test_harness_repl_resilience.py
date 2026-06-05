import urllib.error
from ai4science.harness import repl
from ai4science.harness.adapters import factory


def test_next_available_brand_skips_current_picks_reachable(monkeypatch):
    monkeypatch.setattr(factory, "harness_available", lambda b: b == "gemini")
    nb, nm = repl._next_available_brand("openai")
    assert nb == "gemini" and nm


def test_next_available_brand_none_when_only_current_reachable(monkeypatch):
    monkeypatch.setattr(factory, "harness_available", lambda b: b == "openai")
    assert repl._next_available_brand("openai") is None


def test_next_available_brand_none_when_nothing_reachable(monkeypatch):
    monkeypatch.setattr(factory, "harness_available", lambda b: False)
    assert repl._next_available_brand("openai") is None


def test_clean_turn_error_is_one_line_with_status():
    e = urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)
    s = repl._clean_turn_error(e)
    assert "\n" not in s
    assert "401" in s or "Unauthorized" in s


def test_clean_turn_error_bare_exception():
    assert repl._clean_turn_error(RuntimeError("boom")) == "RuntimeError: boom"

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


def test_infer_backend_from_model():
    assert repl._infer_backend("gemini-3.1-pro-preview") == "gemini"
    assert repl._infer_backend("gpt-5.5") == "openai"
    assert repl._infer_backend("claude-opus-4-8") == "anthropic"
    assert repl._infer_backend("totally-unknown-model") is None


def test_pick_brand_infers_backend_from_model_only():
    assert repl._pick_brand(None, "gemini-3.1-pro-preview") == (
        "gemini", "gemini-3.1-pro-preview")


def test_pick_brand_explicit_backend_and_model_passthrough():
    assert repl._pick_brand("gemini", "x-model") == ("gemini", "x-model")

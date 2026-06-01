from ai4science.harness.adapters import creds
from ai4science.harness.adapters._dotdict import dot


def test_dot_nested():
    o = dot({"choices": [{"delta": {"content": "hi"}}]})
    assert o.choices[0].delta.content == "hi"
    assert o.usage is None        # missing attr -> None


def test_resolve_gemini(monkeypatch):
    from ai4science.llm import gemini
    monkeypatch.setattr(gemini, "resolve_base", lambda: "https://g/v1beta/openai/")
    monkeypatch.setattr(gemini, "resolve_key", lambda: "GKEY")
    c = creds.resolve("gemini")
    assert c.kind == "openai_compat" and c.api_key == "GKEY"
    assert c.base_url.rstrip("/").endswith("chat/completions") or "chat/completions" in c.base_url
    assert creds.available("gemini") is True


def test_resolve_anthropic_keyed(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "AKEY")
    c = creds.resolve("anthropic")
    assert c.kind == "anthropic" and c.api_key == "AKEY"
    assert creds.available("anthropic") is True


def test_anthropic_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert creds.available("anthropic") is False

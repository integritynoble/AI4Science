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
    assert c.auth == "api_key"
    assert creds.available("anthropic") is True


def test_anthropic_falls_back_to_subscription(monkeypatch):
    # No API key, but a Claude Code subscription token is present → available
    # via OAuth (auth='oauth'). This is the `--auth subscription` path.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from ai4science.harness.adapters import claude_sub_creds as csc
    monkeypatch.setattr(csc, "subscription_available", lambda: True)
    monkeypatch.setattr(csc, "subscription_token", lambda: "sk-oauth-xyz")
    c = creds.resolve("anthropic")
    assert c.auth == "oauth" and c.api_key == "sk-oauth-xyz"
    assert creds.available("anthropic") is True


def test_anthropic_unavailable_without_key_or_subscription(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from ai4science.harness.adapters import claude_sub_creds as csc
    monkeypatch.setattr(csc, "subscription_available", lambda: False)
    assert creds.available("anthropic") is False

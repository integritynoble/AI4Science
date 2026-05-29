"""Tests for the generic OpenAI-compatible client (deepseek/qwen via Vertex,
openai by api-key) — #5 tail. No live calls; urlopen is mocked."""
from __future__ import annotations

import io
import json

import pytest

from ai4science.llm import openai_compat as oc


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    # no user keys / comparegpt by default
    monkeypatch.setenv("AI4SCIENCE_USER_CONFIG", str(tmp_path / "user.json"))
    monkeypatch.setenv("AI4SCIENCE_KEYS", str(tmp_path / "keys.json"))
    monkeypatch.setenv("AI4SCIENCE_COMPAREGPT_ENV", str(tmp_path / "nope.env"))
    for v in ("OPENAI_API_KEY", "GOOGLE_ACCESS_TOKEN", "AI4SCIENCE_VERTEX_TOKEN",
              "AI4SCIENCE_VERTEX_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        monkeypatch.delenv(v, raising=False)


def test_vertex_backends_unavailable_without_creds(monkeypatch):
    # Simulate no GCP creds (no env token, no gcloud project) → unavailable.
    monkeypatch.setattr(oc, "_vertex_project", lambda: None)
    monkeypatch.setattr(oc, "_vertex_token", lambda: None)
    assert oc.is_available("deepseek") is False
    assert oc.is_available("qwen") is False
    assert oc.resolve_base("deepseek") == ""        # no project


def test_vertex_base_built_from_project_and_token(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_VERTEX_PROJECT", "my-proj")
    monkeypatch.setenv("AI4SCIENCE_VERTEX_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_ACCESS_TOKEN", "ya29.fake")
    base = oc.resolve_base("deepseek")
    assert base == ("https://us-central1-aiplatform.googleapis.com/v1beta1/"
                    "projects/my-proj/locations/us-central1/endpoints/openapi")
    assert oc.resolve_key("deepseek") == "ya29.fake"
    assert oc.is_available("deepseek") is True


def test_openai_apikey_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-123")
    assert oc.resolve_key("openai") == "sk-env-123"
    assert oc.is_available("openai") is True


def test_chat_raises_without_key():
    with pytest.raises(RuntimeError):
        oc.chat("openai", [{"role": "user", "content": "hi"}])


def test_chat_success_mocked(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-123")
    payload = {"choices": [{"message": {"content": "hello"}}],
               "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}

    def _fake_urlopen(req, timeout=0):
        # confirm the request carries the key + targets chat/completions
        assert req.headers["Authorization"] == "Bearer sk-env-123"
        assert req.full_url.endswith("/chat/completions")
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(oc.urllib.request, "urlopen", _fake_urlopen)

    text, usage = oc.chat("openai", [{"role": "user", "content": "hi"}], model="gpt-x")
    assert text == "hello"
    assert usage["total_tokens"] == 5

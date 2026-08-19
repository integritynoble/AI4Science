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


# ── pwm_qwen: a SECOND api-key backend (physicsworldmodel.org gateway) ──────
def test_pwm_qwen_backend_config():
    # a NEW, additional backend key — not a rename of anything existing
    assert "pwm_qwen" in oc.BACKENDS
    cfg = oc.BACKENDS["pwm_qwen"]
    assert cfg["base"] == "https://physicsworldmodel.org/qwen/v1"
    assert cfg["key_envs"] == ("PWM_QWEN_API_KEY",)
    assert cfg["default_model"] == "qwen3.8:27b"
    # it is an api-key backend, NOT a Vertex one
    assert oc._is_vertex("pwm_qwen") is False


def test_pwm_qwen_resolves(monkeypatch):
    monkeypatch.setenv("PWM_QWEN_API_KEY", "pk-1")
    assert oc.resolve_base("pwm_qwen") == "https://physicsworldmodel.org/qwen/v1"
    assert oc.resolve_key("pwm_qwen") == "pk-1"
    assert oc.default_model("pwm_qwen") == "qwen3.8:27b"
    assert oc.is_available("pwm_qwen") is True


def test_existing_qwen_entry_still_vertex_maas_unchanged():
    # the ORIGINAL qwen entry must remain byte-identical Vertex MaaS config,
    # untouched by the pwm_qwen addition
    assert oc.BACKENDS["qwen"] == {
        "vertex": True,
        "location": "global",
        "default_model": "qwen/qwen3-235b-a22b-instruct-2507-maas",
    }
    assert oc._is_vertex("qwen") is True
    # and it exposes no api-key surface (that belongs to pwm_qwen alone)
    assert "base" not in oc.BACKENDS["qwen"]
    assert "key_envs" not in oc.BACKENDS["qwen"]


def test_chat_with_meta_surfaces_provider_ids(monkeypatch):
    monkeypatch.setenv("PWM_QWEN_API_KEY", "pk-1")
    monkeypatch.setenv("AI4SCIENCE_PWM_QWEN_API_BASE", "http://local/v1")
    payload = {"id": "resp-77", "model": "qwen3.8:27b",
               "system_fingerprint": "fp-abc",
               "choices": [{"message": {"content": "hey"}}],
               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}

    def _fake_urlopen(req, timeout=0):
        return io.BytesIO(json.dumps(payload).encode())
    monkeypatch.setattr(oc.urllib.request, "urlopen", _fake_urlopen)

    text, usage, meta = oc.chat_with_meta("pwm_qwen",
                                          [{"role": "user", "content": "hi"}])
    assert text == "hey"
    assert usage["total_tokens"] == 2
    assert meta["backend"] == "pwm_qwen"
    assert meta["observed_model"] == "qwen3.8:27b"
    assert meta["system_fingerprint"] == "fp-abc"
    assert meta["response_id"] == "resp-77"


def test_chat_return_shape_unchanged(monkeypatch):
    # chat() must still return exactly (text, usage) — two values, no third
    monkeypatch.setenv("PWM_QWEN_API_KEY", "pk-1")
    monkeypatch.setenv("AI4SCIENCE_PWM_QWEN_API_BASE", "http://local/v1")
    payload = {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}
    monkeypatch.setattr(oc.urllib.request, "urlopen",
                        lambda req, timeout=0: io.BytesIO(json.dumps(payload).encode()))
    result = oc.chat("pwm_qwen", [{"role": "user", "content": "hi"}])
    assert isinstance(result, tuple) and len(result) == 2

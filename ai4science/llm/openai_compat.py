"""Generic OpenAI-compatible chat client (Kimi, Qwen, OpenAI-by-key, …).

Many providers expose an OpenAI-compatible /chat/completions endpoint, so one
client covers them all given (base_url, api_key, model). Keys are resolved at
runtime — the user's stored key (from `ai4science login`) first, then env vars —
and never committed to the repo.

Closes the #5 tail: Kimi/Qwen backends + api-key execution.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Dict, List, Optional, Tuple

# backend → endpoint defaults (base URL + env var names + default model).
# Model defaults are overridable with AI4SCIENCE_<BACKEND>_MODEL — adjust if the
# provider renames models.
# DeepSeek + Qwen are served via Google Vertex AI (Model Garden / MaaS), using
# its OpenAI-compatible endpoint. Vertex needs GCP creds (project + access
# token); without them these backends are simply unavailable (not routed).
# Model ids are overridable with AI4SCIENCE_<BACKEND>_MODEL.
BACKENDS: Dict[str, Dict] = {
    "deepseek": {
        "vertex": True,
        "default_model": "deepseek-ai/deepseek-r1-0528-maas",
    },
    "qwen": {
        "vertex": True,
        "default_model": "qwen/qwen3-235b-a22b-instruct-2507-maas",
    },
    "openai": {   # api-key path (alternative to the codex subscription)
        "base": "https://api.openai.com/v1",
        "key_envs": ("OPENAI_API_KEY",),
        "default_model": "gpt-5.5",
    },
}


def _comparegpt_key(key_env: str) -> Optional[str]:
    """Read a key from the comparegpt .env (the gateway that holds shared keys)."""
    try:
        from ai4science.llm.gemini import _read_env_val, _comparegpt_env
        return _read_env_val(_comparegpt_env(), key_env)
    except Exception:
        return None


# ── Vertex AI helpers (GCP project + access token) ──────────────────────
def _vertex_project() -> Optional[str]:
    for env in ("AI4SCIENCE_VERTEX_PROJECT", "GOOGLE_CLOUD_PROJECT", "GCP_PROJECT"):
        v = os.environ.get(env)
        if v:
            return v
    return None


def _vertex_location() -> str:
    return (os.environ.get("AI4SCIENCE_VERTEX_LOCATION")
            or os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1")


def _vertex_token() -> Optional[str]:
    tok = os.environ.get("GOOGLE_ACCESS_TOKEN") or os.environ.get("AI4SCIENCE_VERTEX_TOKEN")
    if tok:
        return tok
    import shutil
    import subprocess
    if not shutil.which("gcloud"):
        return None
    try:
        r = subprocess.run(["gcloud", "auth", "print-access-token"],
                           capture_output=True, text=True, timeout=20, check=False)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:
        return None


def _is_vertex(backend: str) -> bool:
    return bool(BACKENDS.get(backend, {}).get("vertex"))


def resolve_key(backend: str) -> Optional[str]:
    """The credential: Vertex access token for vertex backends; else the user's
    stored key (onboarding) → env vars → comparegpt .env."""
    if _is_vertex(backend):
        return _vertex_token()
    try:
        from ai4science import user
        k = user.get_api_key(backend)
        if k:
            return k
    except Exception:
        pass
    cfg = BACKENDS.get(backend, {})
    for env in (f"AI4SCIENCE_{backend.upper()}_API_KEY", *cfg.get("key_envs", ())):
        v = os.environ.get(env)
        if v:
            return v
    for env in cfg.get("key_envs", ()):   # comparegpt gateway fallback
        v = _comparegpt_key(env)
        if v:
            return v
    return None


def resolve_base(backend: str) -> str:
    override = os.environ.get(f"AI4SCIENCE_{backend.upper()}_API_BASE")
    if override:
        return override
    if _is_vertex(backend):
        proj, loc = _vertex_project(), _vertex_location()
        if not proj:
            return ""
        return (f"https://{loc}-aiplatform.googleapis.com/v1beta1/projects/"
                f"{proj}/locations/{loc}/endpoints/openapi")
    return BACKENDS.get(backend, {}).get("base", "")


def default_model(backend: str) -> str:
    cfg = BACKENDS.get(backend, {})
    return os.environ.get(f"AI4SCIENCE_{backend.upper()}_MODEL") or cfg.get("default_model", "")


def is_available(backend: str) -> bool:
    return bool(resolve_key(backend) and resolve_base(backend))


def chat(backend: str, messages: List[Dict[str, str]], model: Optional[str] = None,
         timeout: int = 120) -> Tuple[str, Dict]:
    """Send a chat completion to an OpenAI-compatible backend. Returns
    (text, usage). Raises RuntimeError if no key or on HTTP error."""
    key = resolve_key(backend)
    if not key:
        envs = BACKENDS.get(backend, {}).get("key_envs", ("<env>",))
        raise RuntimeError(f"no API key for {backend} "
                           f"(run `ai4science login` or set {envs[0]})")
    base = resolve_base(backend)
    model = model or default_model(backend)
    req = urllib.request.Request(
        base.rstrip("/") + "/chat/completions",
        data=json.dumps({"model": model, "messages": messages}).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 # Some gateways (Together via Cloudflare) reject the default
                 # urllib UA with 403/1010; present a normal client UA.
                 "User-Agent": "ai4science/0.1 (+https://physicsworldmodel.org)"},
    )
    try:
        r = json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read()[:200].decode('utf-8', 'replace')}")
    return r["choices"][0]["message"]["content"], r.get("usage", {})

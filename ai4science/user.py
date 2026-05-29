"""User onboarding / preferences — how the agent is powered (points 4–6, 11).

Two ways to power AI4Science:

  power = "own"    → the user's OWN LLM (subscription or API key). Usage runs on
                     the user's account; no PWM is spent. Preferred over wallet
                     providers (point 11).
  power = "wallet" → pay per use from the local hot-key wallet's PWM balance via
                     a wallet-bound provider (points 6, 9).

Config:  ~/.config/ai4science/user.json
API keys: ~/.config/ai4science/keys.json  (chmod 600 — local secrets)
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Dict, Optional

# Providers a user can log into (point 5).
PROVIDERS = ("anthropic", "openai", "gemini", "kimi", "qwen")
AUTH_METHODS = ("subscription", "api_key")


def _base() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science"


def config_path() -> Path:
    return Path(os.environ.get("AI4SCIENCE_USER_CONFIG", _base() / "user.json"))


def keys_path() -> Path:
    return Path(os.environ.get("AI4SCIENCE_KEYS", _base() / "keys.json"))


def load() -> Dict:
    p = config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save(cfg: Dict) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


def _load_keys() -> Dict[str, str]:
    p = keys_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def set_api_key(provider: str, key: str) -> None:
    """Store an API key locally with 0600 perms."""
    keys = _load_keys()
    keys[provider] = key
    p = keys_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(keys, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)   # 600
    except OSError:
        pass


def get_api_key(provider: str) -> Optional[str]:
    return _load_keys().get(provider)


def login_own(provider: str, auth: str, api_key: Optional[str] = None) -> Dict:
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; one of {PROVIDERS}")
    if auth not in AUTH_METHODS:
        raise ValueError(f"unknown auth {auth!r}; one of {AUTH_METHODS}")
    if auth == "api_key":
        if not api_key:
            raise ValueError("api_key auth requires a key")
        set_api_key(provider, api_key)
    cfg = {"power": "own", "provider": provider, "auth": auth,
           "api_key_set": auth == "api_key"}
    save(cfg)
    return cfg


def login_wallet() -> Dict:
    cfg = {"power": "wallet"}
    save(cfg)
    return cfg


def logout() -> None:
    p = config_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def preferred_backend() -> Optional[str]:
    """If the user logged in with their own LLM, the backend to prefer (point 11)."""
    cfg = load()
    return cfg.get("provider") if cfg.get("power") == "own" else None

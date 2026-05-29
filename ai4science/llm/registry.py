"""Wallet-bound LLM-provider registry.

Mirrors the compute-provider registry, but for *LLM* token supply: a provider
binds a wallet address to an LLM backend (anthropic / openai / gemini / …) and
an auth method (subscription / api_key / comparegpt). Usage revenue accrues to
that wallet; the half-price multiplier reflects subscription economics (point 9
of the design).

Phase 1 (founder tier): the founder edits the registry directly. Community
providers later require a signed binding proof (reserved field), and define
their own per-token prices.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ai4science.compute.registry import is_valid_eth_address

# Known LLM backends and auth methods (extensible).
BACKENDS = ("anthropic", "openai", "gemini", "kimi", "qwen")
AUTH_METHODS = ("subscription", "api_key", "comparegpt")


class LLMProvider(BaseModel):
    """A wallet-bound LLM token provider."""
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=2, max_length=100)
    wallet_address: str = Field(description="0x address that usage revenue accrues to")
    backend: str = Field(description="anthropic | openai | gemini | kimi | qwen")
    auth: str = Field(default="subscription", description="subscription | api_key | comparegpt")
    models: List[str] = Field(default_factory=lambda: ["*"],
                              description="model ids served, or ['*'] for any from the backend")
    price_multiplier: float = Field(
        default=1.0,
        description="fraction of official per-token price (0.5 = half, for subscriptions)")
    label: str = Field(default="", max_length=200)
    status: str = Field(default="active")          # active | disabled
    trust_tier: str = Field(default="founder")     # founder | approved | open
    binding_proof: Optional[str] = Field(default=None,
                                         description="SIWE signature (community tiers; reserved)")

    @field_validator("wallet_address")
    @classmethod
    def _check_addr(cls, v: str) -> str:
        if not is_valid_eth_address(v):
            raise ValueError(f"invalid Ethereum address: {v!r} (expected 0x + 40 hex chars)")
        return v

    @field_validator("backend")
    @classmethod
    def _check_backend(cls, v: str) -> str:
        if v not in BACKENDS:
            raise ValueError(f"unknown backend {v!r}; expected one of {BACKENDS}")
        return v

    @field_validator("auth")
    @classmethod
    def _check_auth(cls, v: str) -> str:
        if v not in AUTH_METHODS:
            raise ValueError(f"unknown auth {v!r}; expected one of {AUTH_METHODS}")
        return v


def default_registry_path() -> Path:
    """~/.config/ai4science/llm_providers.json, overridable via env."""
    override = os.environ.get("AI4SCIENCE_LLM_REGISTRY")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science" / "llm_providers.json"


def load_registry(path: Optional[Path] = None) -> List[LLMProvider]:
    path = path or default_registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [LLMProvider.model_validate(p) for p in data.get("providers", [])]


def save_registry(providers: List[LLMProvider], path: Optional[Path] = None) -> Path:
    path = path or default_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "0.1", "providers": [p.model_dump() for p in providers]}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def add_provider(provider: LLMProvider, path: Optional[Path] = None) -> List[LLMProvider]:
    """Add or replace a provider (keyed by provider_id) and persist."""
    providers = [p for p in load_registry(path) if p.provider_id != provider.provider_id]
    providers.append(provider)
    save_registry(providers, path)
    return providers


def get_provider(provider_id: str, path: Optional[Path] = None) -> Optional[LLMProvider]:
    for p in load_registry(path):
        if p.provider_id == provider_id:
            return p
    return None


def providers_for_backend(backend: str, path: Optional[Path] = None) -> List[LLMProvider]:
    return [p for p in load_registry(path) if p.backend == backend and p.status == "active"]

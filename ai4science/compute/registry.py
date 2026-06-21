"""Wallet-bound compute-provider registry.

A provider is identified by a wallet address; verified-job rewards accrue
to that address. v1 (founder tier) bootstraps trust by the founder
editing the registry directly; community tiers later require a
SIWE-signed binding proof (reserved field).
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ETH_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_valid_eth_address(addr: str) -> bool:
    """Basic format check: 0x + 40 hex chars. (EIP-55 checksum validation
    is deferred — it needs keccak256; we preserve the caller's casing.)"""
    return bool(_ETH_ADDR_RE.match(addr or ""))


class ComputeProvider(BaseModel):
    """A wallet-bound GPU provider."""
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=2, max_length=100)
    wallet_address: str = Field(description="0x-prefixed 40-hex Ethereum address")
    endpoint_kind: str = Field(default="file-inbox")
    endpoint_path: str = Field(description="Shared dir the provider polls for jobs")
    label: str = Field(default="", max_length=200)
    kind: str = Field(default="gpu")               # gpu | cpu
    # Price is native PWM/hour (users pay in PWM). `price_usd_per_hour` is kept
    # only for backward compatibility with older registries (derived to PWM at
    # the $5 peg when the PWM field is unset).
    price_pwm_per_hour: Optional[float] = Field(
        default=None, ge=0.0, description="Provider-set compute price (PWM/hour)")
    price_usd_per_hour: float = Field(default=0.0, ge=0.0,
                                      description="DEPRECATED — legacy USD/hour price")
    max_concurrent: int = Field(default=1, ge=1,
                                description="Max users this server serves at once "
                                            "(a counting semaphore; the rest wait)")
    gpu_capability: Dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active")          # active | disabled
    trust_tier: str = Field(default="founder")     # founder | approved | open
    binding_proof: Optional[str] = Field(default=None,
                                         description="SIWE signature (community tiers; reserved)")

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: str) -> str:
        if v not in ("gpu", "cpu"):
            raise ValueError(f"kind must be 'gpu' or 'cpu', got {v!r}")
        return v

    @field_validator("wallet_address")
    @classmethod
    def _check_addr(cls, v: str) -> str:
        if not is_valid_eth_address(v):
            raise ValueError(f"invalid Ethereum address: {v!r} "
                             "(expected 0x + 40 hex chars)")
        return v   # preserve checksum casing as supplied

    def pwm_per_hour(self) -> float:
        """The provider's price in PWM/hour. Uses the native PWM price when set,
        else derives it from the legacy USD price at the $5 peg."""
        if self.price_pwm_per_hour is not None:
            return float(self.price_pwm_per_hour)
        from ai4science.llm.pricing import PWM_USD
        return round(self.price_usd_per_hour / PWM_USD, 6) if PWM_USD > 0 else 0.0


def default_registry_path() -> Path:
    """~/.config/ai4science/compute_providers.json, overridable via env."""
    override = os.environ.get("AI4SCIENCE_COMPUTE_REGISTRY")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science" / "compute_providers.json"


def load_registry(path: Optional[Path] = None) -> List[ComputeProvider]:
    """Load providers from the registry file (empty list if absent)."""
    path = path or default_registry_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [ComputeProvider.model_validate(p) for p in data.get("providers", [])]


def save_registry(providers: List[ComputeProvider], path: Optional[Path] = None) -> Path:
    path = path or default_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "0.1",
        "providers": [p.model_dump() for p in providers],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def add_provider(provider: ComputeProvider, path: Optional[Path] = None) -> List[ComputeProvider]:
    """Add or replace a provider (keyed by provider_id) and persist."""
    providers = load_registry(path)
    providers = [p for p in providers if p.provider_id != provider.provider_id]
    providers.append(provider)
    save_registry(providers, path)
    return providers


# The founder GPU has two historical ids: the advertised default `founder-gpu`
# (founders.py) and the registered served entry `founder-1-subgpu` (the git-synced
# inbox the box actually polls). They are the SAME machine, so resolve either id
# to whichever is registered — dispatching to `founder-gpu` then reaches the
# inbox the serve loop watches, instead of a local dir nobody serves.
PROVIDER_ALIASES = {
    "founder-gpu": "founder-1-subgpu",
    "founder-1-subgpu": "founder-gpu",
    # Friendly names so any agent can dispatch to "gpu1"/"gpu2"/"modal" directly,
    # instead of having to know the internal ids.
    "gpu1": "founder-1-subgpu",        # sub-GPU #1
    "gpu2": "founder-gpu-2",           # sub-GPU #2 (GCP T4)
    "modal": "modal-gpu",              # Modal serverless GPU
}


def get_provider(provider_id: str, path: Optional[Path] = None) -> Optional[ComputeProvider]:
    regs = load_registry(path)
    for p in regs:
        if p.provider_id == provider_id:
            return p
    alias = PROVIDER_ALIASES.get(provider_id)
    if alias:
        for p in regs:
            if p.provider_id == alias:
                return p
    return None

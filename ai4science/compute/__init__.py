"""AI4Science compute layer — wallet-bound GPU providers.

Phase 0 (founder-only) implementation of
docs/COMPUTE_PROVIDERS_DESIGN.md:

  registry     — wallet-bound provider records
  dispatch     — file-inbox job handshake (agent → GPU provider)
  attribution  — judge-verified reward credits bound to a wallet

Trust model: the deterministic Physics Judge re-verifies every result,
so providers are verified, not trusted. The CLI never moves tokens —
attribution is an off-chain log; on-chain settlement is platform-owned.
"""
from ai4science.compute.registry import (
    ComputeProvider, load_registry, save_registry, add_provider,
    is_valid_eth_address,
)

__all__ = [
    "ComputeProvider",
    "load_registry",
    "save_registry",
    "add_provider",
    "is_valid_eth_address",
]

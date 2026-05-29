"""Wallet-bound LLM providers (Phase 1)."""
from ai4science.llm.registry import (
    LLMProvider, BACKENDS, AUTH_METHODS,
    load_registry, save_registry, add_provider, get_provider,
    providers_for_backend, default_registry_path,
)

__all__ = [
    "LLMProvider", "BACKENDS", "AUTH_METHODS",
    "load_registry", "save_registry", "add_provider", "get_provider",
    "providers_for_backend", "default_registry_path",
]

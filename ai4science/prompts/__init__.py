"""Bundled system prompts (loaded at runtime by agent providers)."""
from importlib import resources


def load_system_prompt(name: str) -> str:
    """Load a Markdown system prompt that ships with the package."""
    pkg_root = resources.files("ai4science")
    return (pkg_root / "prompts" / f"{name}.md").read_text(encoding="utf-8")


__all__ = ["load_system_prompt"]

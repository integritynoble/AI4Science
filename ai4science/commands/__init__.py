"""ai4science.commands — Typer subcommand modules.

Each module exposes either a single command callable or a sub-app
(``contribute``, ``judge``, ``overseer`` use sub-apps with their own
subcommands; ``chat`` is a single command that opens a REPL).
"""
from ai4science.commands import chat  # noqa: F401 — surface for cli.py

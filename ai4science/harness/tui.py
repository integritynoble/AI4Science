"""Bordered input box — the Claude-Code-style ╭──╮ input frame, for every agent.

Opt-in via AI4SCIENCE_TUI=1 (default stays the plain line-REPL so it can never
regress). Uses prompt_toolkit for a real bordered, multiline, history-aware
input box; falls back to plain input() when the flag is off, stdin isn't a TTY,
or prompt_toolkit is absent.

  read_input(prompt, mode) -> str        # one bordered prompt; raises EOFError/
                                         # KeyboardInterrupt like input()
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# Claude coral for the frame (matches the working star / ⏺ marker).
_CORAL = "ansibrightred"   # closest named pt color; overridden by the rgb style below


def tui_enabled() -> bool:
    if str(os.environ.get("AI4SCIENCE_TUI", "")).strip().lower() not in (
            "1", "true", "yes", "on"):
        return False
    if not sys.stdin.isatty():
        return False
    try:
        import prompt_toolkit  # noqa: F401
        return True
    except Exception:
        return False


def _history_path(mode: str) -> Optional[Path]:
    try:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ai4science"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"tui_history_{mode}"
    except Exception:
        return None


def read_input(prompt: str = "› ", mode: str = "chat") -> str:
    """Bordered TUI input when enabled, else plain input(prompt)."""
    if not tui_enabled():
        return input(prompt)
    try:
        return _bordered(prompt, mode)
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        # any TUI hiccup → never trap the user; fall back to a normal prompt
        return input(prompt)


def _bordered(prompt: str, mode: str) -> str:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import Frame, TextArea
    from prompt_toolkit.styles import Style
    from prompt_toolkit.history import FileHistory

    hp = _history_path(mode)
    ta = TextArea(
        height=1, multiline=True, wrap_lines=True, prompt=prompt,
        history=FileHistory(str(hp)) if hp else None,
        style="class:input",
    )
    title = [("class:title", f" ai4science · {mode} ")]
    body = HSplit([
        Frame(ta, title=title),
        Window(FormattedTextControl(
            [("class:hint", " Enter ⏎ send · Alt+Enter newline · ↑/↓ history · Ctrl-C exit ")]),
            height=1),
    ])

    kb = KeyBindings()
    out = {"text": None}

    @kb.add("enter")
    def _(event):
        out["text"] = ta.text
        event.app.exit()

    @kb.add("escape", "enter")   # Alt/Option+Enter → newline
    def _(event):
        ta.buffer.insert_text("\n")

    @kb.add("c-c")
    def _(event):
        event.app.exit(exception=KeyboardInterrupt)

    @kb.add("c-d")
    def _(event):
        if not ta.text:
            event.app.exit(exception=EOFError)

    style = Style.from_dict({
        "frame.border": "fg:#d7875f",     # Claude coral box
        "frame.title": "fg:#d7875f bold",
        "input": "",
        "hint": "fg:#8a8a8a",
    })

    app = Application(layout=Layout(body, focused_element=ta),
                      key_bindings=kb, style=style, full_screen=False,
                      mouse_support=False)
    app.run()
    txt = out["text"]
    if txt is None:
        raise KeyboardInterrupt
    return txt

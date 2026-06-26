"""The full bordered TUI is the default on a real terminal; env opts out."""
import sys

from ai4science.harness import tui


def _tty(monkeypatch, stdin=True, stdout=True):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: stdin, raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: stdout, raising=False)


def test_default_is_full_on_tty(monkeypatch):
    _tty(monkeypatch)
    monkeypatch.delenv("AI4SCIENCE_TUI", raising=False)
    assert tui.tui_mode() == "full"


def test_explicit_full(monkeypatch):
    _tty(monkeypatch)
    monkeypatch.setenv("AI4SCIENCE_TUI", "full")
    assert tui.tui_mode() == "full"


def test_box_tier(monkeypatch):
    _tty(monkeypatch)
    for v in ("1", "true", "yes", "on", "box"):
        monkeypatch.setenv("AI4SCIENCE_TUI", v)
        assert tui.tui_mode() == "box", v


def test_opt_out(monkeypatch):
    _tty(monkeypatch)
    for v in ("0", "false", "no", "off", "plain"):
        monkeypatch.setenv("AI4SCIENCE_TUI", v)
        assert tui.tui_mode() == "off", v


def test_off_without_tty(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_TUI", raising=False)
    _tty(monkeypatch, stdin=False, stdout=True)
    assert tui.tui_mode() == "off"
    _tty(monkeypatch, stdin=True, stdout=False)   # piped stdout must stay plain
    assert tui.tui_mode() == "off"


def test_tui_enabled_only_gates_box(monkeypatch):
    _tty(monkeypatch)
    monkeypatch.setenv("AI4SCIENCE_TUI", "full")
    assert tui.tui_enabled() is False     # full routes via the active screen
    monkeypatch.setenv("AI4SCIENCE_TUI", "box")
    assert tui.tui_enabled() is True      # prompt_toolkit is a test dep
    monkeypatch.setenv("AI4SCIENCE_TUI", "off")
    assert tui.tui_enabled() is False


# ── _resolve_fullscreen: POSIX=inline, Windows=alt-screen, env overrides ──────

def test_fullscreen_default_posix_is_inline(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_TUI_INLINE", raising=False)
    monkeypatch.delenv("AI4SCIENCE_TUI_FULLSCREEN", raising=False)
    monkeypatch.setattr(tui.os, "name", "posix")
    assert tui._resolve_fullscreen() is False


def test_fullscreen_default_windows_is_altscreen(monkeypatch):
    # Windows must own the alt-screen or Windows Terminal steals the arrows.
    monkeypatch.delenv("AI4SCIENCE_TUI_INLINE", raising=False)
    monkeypatch.delenv("AI4SCIENCE_TUI_FULLSCREEN", raising=False)
    monkeypatch.setattr(tui.os, "name", "nt")
    assert tui._resolve_fullscreen() is True


def test_fullscreen_inline_env_forces_inline_even_on_windows(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_TUI_INLINE", "1")
    monkeypatch.delenv("AI4SCIENCE_TUI_FULLSCREEN", raising=False)
    monkeypatch.setattr(tui.os, "name", "nt")
    assert tui._resolve_fullscreen() is False


def test_fullscreen_env_forces_altscreen_even_on_posix(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_TUI_FULLSCREEN", "1")
    monkeypatch.delenv("AI4SCIENCE_TUI_INLINE", raising=False)
    monkeypatch.setattr(tui.os, "name", "posix")
    assert tui._resolve_fullscreen() is True

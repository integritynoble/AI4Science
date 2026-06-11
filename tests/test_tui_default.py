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

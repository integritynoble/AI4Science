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


# ── ask_choice text fallback (custom read_input → type the number) ────────────

def test_ask_choice_text_fallback_parses_typed_number():
    captured = {}
    def fake_read_input(prompt, mode):
        captured["prompt"] = prompt
        return "1"
    idx = tui.ask_choice("Proceed?", ["Yes", "No-always", "No"],
                         read_input=fake_read_input)
    assert idx == 0
    # The prompt must tell the user to TYPE the number (Windows arrow confusion).
    assert "Type a number" in captured["prompt"]
    assert "1." in captured["prompt"] and "3." in captured["prompt"]


def test_ask_choice_text_fallback_accepts_yes_word():
    idx = tui.ask_choice("Proceed?", ["Yes", "No"],
                         read_input=lambda p, m: "yes")
    assert idx == 0


def test_ask_choice_text_fallback_invalid_is_last_option():
    # Garbage → the safe last option ("No" for a yes/no confirm).
    idx = tui.ask_choice("Proceed?", ["Yes", "No"],
                         read_input=lambda p, m: "garbage")
    assert idx == 1


# ── experimental VT input flag (AI4SCIENCE_TUI_VT_INPUT=1, Windows) ───────────

def test_vt_input_forced_requires_windows_and_flag(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_TUI_VT_INPUT", "1")
    monkeypatch.setattr(tui.os, "name", "posix")
    assert tui._vt_input_forced() is False          # not Windows → off
    monkeypatch.setattr(tui.os, "name", "nt")
    assert tui._vt_input_forced() is True           # Windows + flag → on
    monkeypatch.delenv("AI4SCIENCE_TUI_VT_INPUT", raising=False)
    assert tui._vt_input_forced() is False           # no flag → off


def test_vt_flag_switches_picker_back_to_visual(monkeypatch):
    # With VT input forced, arrows should work → use the visual picker, not the
    # typed-number prompt.
    monkeypatch.setenv("AI4SCIENCE_TUI_VT_INPUT", "1")
    monkeypatch.delenv("AI4SCIENCE_TYPED_CHOICE", raising=False)
    monkeypatch.setattr(tui.os, "name", "nt")
    assert tui._use_typed_choice() is False
    # Without the VT flag, Windows defaults to the typed-number picker.
    monkeypatch.delenv("AI4SCIENCE_TUI_VT_INPUT", raising=False)
    assert tui._use_typed_choice() is True


def test_experimental_vt_input_none_when_flag_off(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_TUI_VT_INPUT", raising=False)
    assert tui._experimental_vt_input() is None


def test_experimental_vt_input_degrades_gracefully(monkeypatch):
    # Flag on + faked Windows, but Win32Input construction fails off-Windows →
    # must return None (fall back to default input), never raise.
    monkeypatch.setenv("AI4SCIENCE_TUI_VT_INPUT", "1")
    monkeypatch.setattr(tui.os, "name", "nt")
    assert tui._experimental_vt_input() is None

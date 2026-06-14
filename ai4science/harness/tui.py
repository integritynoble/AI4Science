"""Claude-Code-style input for every agent — a borderless two-line prompt.

The full-screen TUI is the DEFAULT on a real terminal (like the product): a
managed transcript pane above a borderless input that grows 1→N as you type,
with one info line (mode · status · shortcuts) beneath it — no box frame.
`AI4SCIENCE_TUI` tunes it: `full` (default), `1`/`box` for the bordered single
input line (no pane), `0`/`off`/`plain` for the classic line-REPL. Uses
prompt_toolkit for a real multiline, history-aware input; falls back to plain
input() when opted out, stdin/stdout isn't a TTY, or prompt_toolkit is absent.

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

# Friendly DISPLAY names for modes (the internal id is unchanged — only the
# label shown in the info line / input header is mapped).
_MODE_DISPLAY = {"claude-code": "Claude"}


def _display_mode(mode: str) -> str:
    return _MODE_DISPLAY.get(mode, mode)


def tui_enabled() -> bool:
    """Bordered single-prompt input (box tier). Full-screen routes through the
    active screen in read_input, so this only gates the box."""
    if tui_mode() != "box":
        return False
    try:
        import prompt_toolkit  # noqa: F401
        return True
    except Exception:
        return False


def input_box_rows(text: str, cols: int, max_rows: int = 10) -> int:
    """Visual rows a borderless input needs for `text` at terminal width `cols`,
    clamped to [1, max_rows]. Grows like Claude Code's prompt: one row per
    logical line, plus extra rows for any line that soft-wraps."""
    inner = max(cols - 3, 10)            # leave room for the "❯ " prompt
    rows = 0
    for line in text.split("\n"):
        rows += max(1, -(-len(line) // inner))   # ceil(len/inner), min 1 per line
    return min(max(rows, 1), max_rows)


def _grow_height(get_text, max_rows: int = 10):
    """prompt_toolkit height callable: size the input to its content so the
    two-line prompt grows 1→N as you type (no fixed-height box)."""
    from prompt_toolkit.application import get_app
    from prompt_toolkit.layout.dimension import Dimension

    def _h():
        try:
            cols = get_app().output.get_size().columns
        except Exception:
            cols = 80
        r = input_box_rows(get_text(), cols, max_rows)
        # Exact height (min==max): the input is precisely its content rows so the
        # transcript pane absorbs all slack and the input stays flush at the
        # bottom — no inflated blank box.
        return Dimension(min=r, max=r, preferred=r)
    return _h


# Big pastes collapse to a placeholder (Claude Code parity); tunable via env.
_PASTE_MIN_LINES = int(os.environ.get("AI4SCIENCE_PASTE_MIN_LINES", "4"))
_PASTE_MIN_CHARS = int(os.environ.get("AI4SCIENCE_PASTE_MIN_CHARS", "400"))


def _attach_paste_collapse(ta, kb):
    """Claude-Code-style paste collapsing for an input TextArea.

    A large bracketed paste is shown as `[Pasted text #N +M lines]` in the input
    (so the box stays readable) while the FULL content is restored on submit.
    Small pastes insert normally. Returns expand(displayed_text) -> full_text."""
    from prompt_toolkit.keys import Keys
    store: dict = {}

    @kb.add(Keys.BracketedPaste)
    def _(event):
        data = event.data or ""
        nlines = data.count("\n") + 1
        if nlines >= _PASTE_MIN_LINES or len(data) >= _PASTE_MIN_CHARS:
            idx = len(store) + 1
            placeholder = f"[Pasted text #{idx} +{nlines} lines]"
            store[placeholder] = data
            ta.buffer.insert_text(placeholder)
        else:
            ta.buffer.insert_text(data)

    def expand(text: str) -> str:
        for placeholder, data in store.items():
            text = text.replace(placeholder, data)
        return text

    return expand


def _history_path(mode: str) -> Optional[Path]:
    try:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "ai4science"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"tui_history_{mode}"
    except Exception:
        return None


def read_input(prompt: str = "› ", mode: str = "chat", status: str = "") -> str:
    """Bordered TUI input when enabled, else plain input(prompt).

    `status` is a one-line status bar (e.g. 'model · 7056 PWM · ~/proj') shown
    under the box, like Claude Code's bottom line.
    """
    m = tui_mode()
    if m == "off":
        return input(prompt)
    try:
        import prompt_toolkit  # noqa: F401
    except Exception:
        return input(prompt)
    try:
        # 'full' (default) → inline two-line input (native wheel-scroll + copy);
        # 'box' → the bordered single-line input box.
        return _bordered(prompt, mode, status) if m == "box" \
            else _two_line_inline(prompt, mode, status)
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        # any TUI hiccup → never trap the user; fall back to a normal prompt
        return input(prompt)


def _bordered(prompt: str, mode: str, status: str = "") -> str:
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import Frame, TextArea
    from prompt_toolkit.widgets.base import Border
    from prompt_toolkit.styles import Style
    from prompt_toolkit.history import FileHistory

    # Rounded corners (╭╮╰╯) like Claude Code, instead of the default square set.
    Border.TOP_LEFT, Border.TOP_RIGHT = "╭", "╮"
    Border.BOTTOM_LEFT, Border.BOTTOM_RIGHT = "╰", "╯"

    hp = _history_path(mode)
    ta = TextArea(
        height=1, multiline=True, wrap_lines=True, prompt=prompt,
        history=FileHistory(str(hp)) if hp else None,
        style="class:input",
    )
    title = [("class:title", f"ai4science · {_display_mode(mode)}")]
    rows = [Frame(ta, title=title)]
    if status:
        rows.append(Window(FormattedTextControl(
            [("class:status", f" {status} ")]), height=1))
    rows.append(Window(FormattedTextControl(
        [("class:hint", " Enter ⏎ send · Alt+Enter newline · ↑/↓ history · Ctrl-C exit ")]),
        height=1))
    body = HSplit(rows)

    kb = KeyBindings()
    out = {"text": None}
    _expand = _attach_paste_collapse(ta, kb)

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
        "status": "fg:#a8a8a8",
        "hint": "fg:#8a8a8a",
    })

    app = Application(layout=Layout(body, focused_element=ta),
                      key_bindings=kb, style=style, full_screen=False,
                      mouse_support=False)
    app.run()
    txt = out["text"]
    if txt is None:
        raise KeyboardInterrupt
    return _expand(txt)


def _two_line_inline(prompt: str, mode: str, status: str = "") -> str:
    """Claude-Code-style INLINE two-line input: a coral ❯ prompt framed by a top
    and bottom rule (no box), with one info line, rendered full_screen=False so
    it does NOT take over the terminal. The conversation prints normally above
    it, so the terminal's own scrollback (mouse wheel) and text selection (copy)
    both work — exactly like Claude Code. On submit the widget is erased and the
    line is echoed as `❯ <text>` so the transcript stays clean."""
    from prompt_toolkit import Application
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.widgets import TextArea
    from prompt_toolkit.styles import Style
    from prompt_toolkit.history import FileHistory

    hp = _history_path(mode)
    ta = TextArea(multiline=True, wrap_lines=True,
                  prompt=[("class:prompt", "❯ ")],
                  history=FileHistory(str(hp)) if hp else None, style="class:input")
    ta.window.height = _grow_height(lambda: ta.text)

    def _rule():
        return Window(height=1, char="─", style="class:rule")

    info = f" \x1b[38;5;173mai4science · {_display_mode(mode)}\x1b[0m"
    if status:
        info += f" · \x1b[38;5;245m{status}\x1b[0m"
    info += "   \x1b[38;5;240m⏎ send · ⌥⏎ newline · ↑↓ history · /exit\x1b[0m"

    body = HSplit([
        _rule(),
        ta,
        _rule(),
        Window(FormattedTextControl(ANSI(info)), height=1),
    ])

    kb = KeyBindings()
    out = {"text": None}
    _expand = _attach_paste_collapse(ta, kb)

    @kb.add("enter")
    def _(event):
        out["text"] = ta.text
        ta.buffer.reset(append_to_history=True)
        event.app.exit()

    @kb.add("escape", "enter")
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
        "prompt": "fg:#d7875f bold",
        "rule": "fg:#d7875f",
        "input": "",
    })
    app = Application(layout=Layout(body, focused_element=ta), key_bindings=kb,
                      style=style, full_screen=False, mouse_support=False,
                      erase_when_done=True)
    app.run()
    txt = out["text"]
    if txt is None:
        raise KeyboardInterrupt
    # widget erased → echo the submitted line so it stays in the scrollback.
    # Echo the COLLAPSED text (placeholders) to keep the transcript clean; the
    # FULL pasted content is what we return to the agent.
    sys.stdout.write(f"\x1b[38;5;173m❯\x1b[0m {txt}\n")
    sys.stdout.flush()
    return _expand(txt)


# ════════════════════════════════════════════════════════════════════════════
# Full-screen TUI (the default; AI4SCIENCE_TUI tunes it) — the whole Claude
# Code experience:
# output pane managed by the app, a borderless two-line input at the bottom
# (growing prompt + one info line, no box), with a pulsing working star. The
# existing REPL loops run UNCHANGED
# in a worker thread: their prints land in the pane (stdout redirect) and their
# input()s route here (read_input checks the active screen).
# ════════════════════════════════════════════════════════════════════════════

_ACTIVE = {"screen": None}


def tui_mode() -> str:
    # The full-screen app owns the terminal, so require a real TTY on BOTH
    # ends — `ai4science chat | tee log` must stay a plain pipe-safe REPL.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return "off"
    v = str(os.environ.get("AI4SCIENCE_TUI", "")).strip().lower()
    if v in ("0", "false", "no", "off", "plain"):
        return "off"
    if v in ("1", "true", "yes", "on", "box"):
        return "box"
    return "full"  # default (unset or `full`)


class _StdoutProxy:
    """Routes the REPL's prints into the screen pane. isatty()=False on purpose:
    the inline Spinner checks it and silences itself (the screen has its own
    star in the status bar)."""
    def __init__(self, screen):
        self._s = screen
    def write(self, text):
        if text:
            self._s.append(text)
        return len(text or "")
    def flush(self):
        pass
    def isatty(self):
        return False


class FullScreen:
    _FRAMES = ["✶", "✷", "✸", "✹", "✺", "✹", "✸", "✷"]

    def __init__(self, mode: str, prompt: str = "❯ "):
        import queue
        import threading
        self.mode = mode
        self.prompt = prompt
        self._text = ""                 # raw (ANSI) transcript
        self._inq = queue.Queue()       # Enter → lines for the worker
        self._busy = True
        self._frame_i = 0
        self._status_extra = ""
        self._lock = threading.Lock()
        self._app = None

    # ── worker-side API ────────────────────────────────────────────────────
    def append(self, text: str) -> None:
        with self._lock:
            self._text += text
            if len(self._text) > 400_000:        # keep the pane bounded
                self._text = self._text[-300_000:]
        app = self._app
        if app is not None:
            try:
                app.loop.call_soon_threadsafe(app.invalidate)
            except Exception:
                pass

    def read_input(self, prompt: str = "", status: str = "") -> str:
        if prompt and prompt not in ("❯ ", "> "):
            self.append("\n" + prompt)           # e.g. permission questions
        self._status_extra = status
        self._busy = False
        line = self._inq.get()                   # blocks the WORKER only
        self._busy = True
        if line is None:
            raise EOFError
        self.append(f"\n\x1b[38;5;173m❯\x1b[0m {line}\n")
        return line

    # ── the app ─────────────────────────────────────────────────────────────
    def run(self, worker) -> None:
        """Run the full-screen app; `worker(screen)` runs the REPL loop in a
        background thread with stdout redirected into the pane."""
        # The alt-screen app paints from (0,0) and never needs cursor-position
        # reports. Disable CPR so terminals that don't answer ESC[6n (some
        # SSH/web/CI shells) don't get stuck on prompt_toolkit's repeated
        # "WARNING: …CPR… Press ENTER to continue" loop.
        os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
        import threading
        from prompt_toolkit import Application
        from prompt_toolkit.formatted_text import ANSI
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.layout.containers import HSplit, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.widgets import TextArea
        from prompt_toolkit.styles import Style
        from prompt_toolkit.history import FileHistory

        hp = _history_path(self.mode)
        # Borderless, two-line input like Claude Code: a coral prompt line that
        # grows 1→N as you type, with a single info line beneath it (no box).
        ta = TextArea(multiline=True, wrap_lines=True,
                      prompt=[("class:prompt", self.prompt)],
                      history=FileHistory(str(hp)) if hp else None, style="class:input")
        ta.window.height = _grow_height(lambda: ta.text)

        from prompt_toolkit.application import get_app
        from prompt_toolkit.data_structures import Point
        from prompt_toolkit.mouse_events import MouseEventType

        def _pane_text():
            with self._lock:
                return ANSI(self._text)

        # self._cursor_line: None = follow the latest output (auto-scroll to
        # bottom); an int pins the view there while you wheel back through history.
        self._cursor_line = None

        def _line_count() -> int:
            with self._lock:
                t = self._text
            return max(1, len(t.rstrip("\n").split("\n")))

        def _pane_cursor():
            # An (invisible) cursor the Window scrolls to keep visible. Clamp to
            # the last REAL line — never past it: a too-large y crashes
            # prompt_toolkit's line-wrap scroll with "list index out of range".
            last = _line_count() - 1
            y = last if self._cursor_line is None else min(self._cursor_line, last)
            return Point(x=0, y=max(0, y))

        out_ctrl = FormattedTextControl(_pane_text, get_cursor_position=_pane_cursor)

        def _scroll_pane(up_lines: int) -> None:
            # up_lines > 0 → move the view UP into history; reaching the bottom
            # resumes following the latest output. Used by the wheel AND PageUp/Dn.
            last = _line_count() - 1
            cur = last if self._cursor_line is None else min(self._cursor_line, last)
            nv = cur - up_lines
            self._cursor_line = None if nv >= last else max(0, nv)
            try:
                get_app().invalidate()
            except Exception:
                pass

        def _pane_mouse(mouse_event):
            if mouse_event.event_type == MouseEventType.SCROLL_UP:
                _scroll_pane(3)
            elif mouse_event.event_type == MouseEventType.SCROLL_DOWN:
                _scroll_pane(-3)
            else:
                return NotImplemented          # let other handlers have it
            return None
        out_ctrl.mouse_handler = _pane_mouse

        def _info():
            self._frame_i = (self._frame_i + 1) % len(self._FRAMES)
            star = (f"\x1b[38;5;173m{self._FRAMES[self._frame_i]}\x1b[0m working…  "
                    if self._busy else "")
            mode = f"\x1b[38;5;173mai4science · {_display_mode(self.mode)}\x1b[0m"
            extra = (f" · \x1b[38;5;245m{self._status_extra}\x1b[0m"
                     if self._status_extra else "")
            hints = ("   \x1b[38;5;240m⏎ send · ⌥⏎ newline · PgUp/Dn scroll · "
                     "esc stop · /exit\x1b[0m")
            return ANSI(f" {star}{mode}{extra}{hints}")

        out_win = Window(out_ctrl, wrap_lines=True, always_hide_cursor=True,
                         style="class:pane")
        # Claude-Code-style input framed by ONLY a top + bottom horizontal rule
        # (no left/right verticals); the prompt grows between them.
        def _rule():
            return Window(height=1, char="─", style="class:rule")
        body = HSplit([
            out_win,
            _rule(),                                     # upper horizontal line
            ta,                                          # input (grows; no side borders)
            _rule(),                                     # bottom horizontal line
            Window(FormattedTextControl(_info), height=1),   # info/status line
        ])

        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            text = ta.text
            ta.buffer.reset(append_to_history=True)
            if text.strip().lower() in ("/exit", "/quit", "exit", "quit", "q"):
                self._inq.put(None)
                event.app.exit()
                return
            self._inq.put(text)

        @kb.add("escape", "enter")
        def _(event):
            ta.buffer.insert_text("\n")

        @kb.add("escape")
        def _(event):
            # Esc while the agent is busy → interrupt the running turn (kills
            # a running bash, ends the turn). Non-eager so the Alt+Enter
            # (escape,enter) chord above still matches.
            if self._busy:
                from ai4science.harness import interrupt
                interrupt.request()
                self.append("\n\x1b[2m[esc] interrupting…\x1b[0m\n")

        @kb.add("c-c")
        def _(event):
            self._inq.put(None)
            event.app.exit()

        @kb.add("c-d")
        def _(event):
            if not ta.text:
                self._inq.put(None)
                event.app.exit()

        @kb.add("pageup")          # scroll the transcript without the mouse
        def _(event):
            _scroll_pane(10)

        @kb.add("pagedown")
        def _(event):
            _scroll_pane(-10)

        style = Style.from_dict({
            "prompt": "fg:#d7875f bold",   # coral ❯ like Claude Code
            "rule": "fg:#d7875f",          # coral top/bottom horizontal lines
            # Bright/white body text like Claude Code (explicit coral accents and
            # the dim ⎿ result gutter keep their own colors and override this).
            "pane": "fg:#ffffff",
            "input": "fg:#ffffff",         # what you type is bright too
        })
        # Mouse capture trade-off. DEFAULT OFF so native click-drag text
        # selection / copy works like Claude Code; scroll the transcript with
        # PageUp/PageDown. Set `AI4SCIENCE_TUI_MOUSE=on` to make the WHEEL scroll
        # instead — but that captures the mouse, so copy then needs Shift+drag.
        _mouse = os.environ.get("AI4SCIENCE_TUI_MOUSE", "off").strip().lower() \
            in ("1", "on", "yes", "true")
        self._app = Application(layout=Layout(body, focused_element=ta),
                                key_bindings=kb, style=style, full_screen=True,
                                refresh_interval=0.15, mouse_support=_mouse)

        _ACTIVE["screen"] = self
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = _StdoutProxy(self)          # REPL prints → the pane
        sys.stderr = _StdoutProxy(self)
        done = {"v": False}

        def _work():
            try:
                worker(self)
            except Exception as e:
                self.append(f"\n[tui] worker error: {type(e).__name__}: {e}\n")
            finally:
                done["v"] = True
                app = self._app
                if app is not None:
                    try:
                        app.loop.call_soon_threadsafe(app.exit)
                    except Exception:
                        pass

        t = threading.Thread(target=_work, daemon=True)
        t.start()
        try:
            self._app.run()
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            _ACTIVE["screen"] = None
            if not done["v"]:
                self._inq.put(None)              # unblock a waiting worker
            t.join(timeout=3)


def run_full(mode: str, runner) -> bool:
    """Deprecated alt-screen wrapper. We now render INLINE (the REPL prints to the
    terminal normally and `read_input` shows the two-line inline prompt) so the
    terminal's native scrollback (mouse wheel) and text selection (copy) work,
    like Claude Code. Always return False → the caller runs the REPL directly."""
    return False

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


# Reverse: a display name (or its lowercase) the user types resolves to the id.
_DISPLAY_TO_ID = {v.lower(): k for k, v in _MODE_DISPLAY.items()}   # {"claude": "claude-code"}


def resolve_mode(name: str) -> str:
    """Map a user-typed mode name to its internal id, so `/mode Claude` (the
    display name) resolves to `claude-code`. Unknown names pass through."""
    return _DISPLAY_TO_ID.get((name or "").strip().lower(), name)


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
    # When a persistent composer (run_full) owns the screen, ALL input must come
    # through its queue — the worker thread calls us, the main thread reads keys.
    scr = _ACTIVE.get("screen")
    if scr is not None:
        return scr.read_input(prompt, status)
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


def ask_choice(question: str, options, *, read_input=read_input,
               mode: str = "chat") -> int:
    """Ask the user to pick one of `options`, returning the 0-based index.

    When the persistent composer owns the screen, this is Claude Code's
    arrow-key picker (↑/↓/⏎, or 1/2/3). Otherwise it falls back to a typed
    numeric menu (also accepting the legacy y/n/a aliases). Default / unknown
    answers resolve to the LAST option (the safe 'No')."""
    scr = _ACTIVE.get("screen")
    if scr is not None and getattr(scr, "request_choice", None):
        return scr.request_choice(question, options)
    # Text fallback (box / off mode, or no active screen).
    lines = [question, ""] if question else [""]
    for i, opt in enumerate(options):
        lines.append(f"  {i + 1}. {opt}")
    ans = read_input("\n".join(lines) + "\n❯ ", mode)
    a = (ans or "").strip().lower()
    if a in ("1", "y", "yes"):
        return 0
    if a in ("2", "a", "always"):
        return 1
    if a in ("3", "n", "no", ""):
        return min(2, len(options) - 1)
    try:
        k = int(a) - 1
        if 0 <= k < len(options):
            return k
    except ValueError:
        pass
    return len(options) - 1            # unknown → last (No)


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

    # ↑/↓ navigate a multi-line draft, then step through history at the edges
    # (Claude Code parity — ↑ on an empty prompt recalls your last message).
    @kb.add("up")
    def _(event):
        ta.buffer.auto_up(count=event.arg)

    @kb.add("down")
    def _(event):
        ta.buffer.auto_down(count=event.arg)

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


class _StreamCommit:
    """stdout wrapper that commits ONLY complete lines to the scrollback (via the
    patch_stdout proxy it wraps); the in-progress partial line is handed to the
    screen so it renders in the app's live region — NOT printed onto the pinned
    box's top border. This is what stops token-by-token streaming (no trailing
    newline) from corrupting the box and then vanishing on the next repaint."""
    def __init__(self, inner, screen):
        import threading
        self._inner = inner            # patch_stdout's StdoutProxy
        self._screen = screen
        self._buf = ""
        # The worker thread (streaming) AND the main/app thread (the immediate
        # echo of a just-sent message) both write here — guard the buffer.
        self._lock = threading.Lock()

    def write(self, text):
        if not text:
            return 0
        with self._lock:
            self._buf += text
            partial = self._buf
            if "\n" in self._buf:
                cut = self._buf.rfind("\n") + 1
                whole, self._buf = self._buf[:cut], self._buf[cut:]
                partial = self._buf
                self._inner.write(whole)
                try:
                    self._inner.flush()
                except Exception:
                    pass
        self._screen._set_partial(partial)
        return len(text)

    def commit_partial(self):
        """Flush any dangling partial line to the scrollback (turn boundary)."""
        with self._lock:
            if not self._buf:
                return
            self._inner.write(self._buf + "\n")
            try:
                self._inner.flush()
            except Exception:
                pass
            self._buf = ""
        self._screen._set_partial("")

    def flush(self):
        pass                            # deliberately DON'T flush partials

    def isatty(self):
        return getattr(self._inner, "isatty", lambda: False)()

    def __getattr__(self, k):
        return getattr(self._inner, k)


class FullScreen:
    _FRAMES = ["✶", "✷", "✸", "✹", "✺", "✹", "✸", "✷"]

    def __init__(self, mode: str, prompt: str = "❯ "):
        import queue
        import threading
        self.mode = mode
        self.prompt = prompt
        self._inq = queue.Queue()       # Enter → lines for the worker
        self._busy = True
        self._frame_i = 0
        self._status_extra = ""
        self._app = None
        self._expand = lambda t: t      # paste-collapse expander (set in run)
        self._partial = ""              # in-progress streaming line (live region)
        self._stream = None             # the _StreamCommit proxy (set in run)
        self._choice = None             # active permission picker, or None

    def _invalidate(self) -> None:
        app = self._app
        if app is not None:
            try:
                app.loop.call_soon_threadsafe(app.invalidate)
            except Exception:
                pass

    def _set_partial(self, s: str) -> None:
        self._partial = s
        self._invalidate()

    def request_choice(self, question: str, options) -> int:
        """Block the worker while the user picks an option with ↑/↓/⏎ (or 1/2/3)
        in the box's picker panel. Returns the selected index (0-based)."""
        import queue
        if self._stream is not None:
            self._stream.commit_partial()       # flush any dangling partial line
        q: "queue.Queue" = queue.Queue()
        self._choice = {"q": question, "options": list(options), "sel": 0,
                        "result": q}
        self._busy = False
        self._invalidate()
        idx = q.get()                            # blocks the WORKER only
        self._busy = True
        opts = self._choice["options"] if self._choice else list(options)
        self._choice = None
        self._invalidate()
        if 0 <= idx < len(opts):                 # echo the decision to scrollback
            self.append(f"\n\x1b[38;5;173m❯\x1b[0m {opts[idx]}\n")
        return idx

    # ── worker-side API ────────────────────────────────────────────────────
    def append(self, text: str) -> None:
        # Worker thread → write ABOVE the pinned box. Under patch_stdout this
        # lands in the terminal's native scrollback, so the mouse wheel and
        # click-drag copy keep working (no alt-screen pane to trap them).
        if not text:
            return
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except Exception:
            pass

    def read_input(self, prompt: str = "", status: str = "") -> str:
        # Commit any dangling partial line (a response that didn't end in \n) to
        # the scrollback before we prompt, so it isn't left hanging in the live
        # region or lost.
        if self._stream is not None:
            self._stream.commit_partial()
        if prompt and prompt not in ("❯ ", "> "):
            self.append("\n" + prompt)           # e.g. permission questions
        self._status_extra = status
        self._busy = False
        line = self._inq.get()                   # blocks the WORKER only
        self._busy = True
        if line is None:
            raise EOFError
        # NOTE: the `❯ <line>` echo happens in the Enter handler at SEND time —
        # not here — so a message typed WHILE the agent is busy shows instantly
        # instead of vanishing until the turn ends.
        return line

    # ── the app ─────────────────────────────────────────────────────────────
    def run(self, worker) -> None:
        """Render the pinned composer on the main thread; `worker()` (no args)
        runs the REPL loop in a background thread, reading input through the
        module-level `read_input` (routed here) and printing output ABOVE the
        box via patch_stdout."""
        # Disable CPR so terminals that don't answer ESC[6n (some SSH/web/CI
        # shells) don't get stuck on prompt_toolkit's repeated "WARNING: …CPR…
        # Press ENTER to continue" loop.
        os.environ["PROMPT_TOOLKIT_NO_CPR"] = "1"
        import threading
        from prompt_toolkit import Application
        from prompt_toolkit.formatted_text import ANSI
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout
        from prompt_toolkit.layout.containers import HSplit, Window, ConditionalContainer
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.filters import Condition
        from prompt_toolkit.widgets import TextArea
        from prompt_toolkit.styles import Style
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.patch_stdout import patch_stdout

        hp = _history_path(self.mode)
        # Borderless, two-line input like Claude Code: a coral prompt line that
        # grows 1→N as you type, with a single info line beneath it (no box).
        ta = TextArea(multiline=True, wrap_lines=True,
                      prompt=[("class:prompt", self.prompt)],
                      history=FileHistory(str(hp)) if hp else None, style="class:input")
        ta.window.height = _grow_height(lambda: ta.text)

        def _info():
            self._frame_i = (self._frame_i + 1) % len(self._FRAMES)
            star = (f"\x1b[38;5;173m{self._FRAMES[self._frame_i]}\x1b[0m working…  "
                    if self._busy else "")
            mode = f"\x1b[38;5;173mai4science · {_display_mode(self.mode)}\x1b[0m"
            extra = (f" · \x1b[38;5;245m{self._status_extra}\x1b[0m"
                     if self._status_extra else "")
            hints = ("   \x1b[38;5;240m⏎ send · ⌥⏎ newline · ↑ edit · esc stop · /exit\x1b[0m")
            return ANSI(f" {star}{mode}{extra}{hints}")

        # Live region: the in-progress streaming line (no trailing newline yet).
        # It renders on a SINGLE, FIXED row just above the box — showing the
        # tail (most-recent tokens) so the box NEVER moves as the line grows /
        # wraps. A complete line commits to the scrollback (one smooth scroll).
        # The row is reserved only while a turn is in progress (busy), so the
        # idle composer has no gap.
        def _partial_text():
            p = self._partial.rstrip("\n")
            if not p:
                return ANSI("")
            if len(p) > 200:                 # keep it to one row: show the tail
                p = "…" + p[-200:]
            try:
                return ANSI(p)
            except Exception:
                return p

        def _partial_height():
            return 1 if (self._busy or self._partial) else 0
        partial_win = Window(FormattedTextControl(_partial_text),
                             height=_partial_height, wrap_lines=False,
                             style="class:input")

        # Permission picker (Claude Code's arrow-key menu). When self._choice is
        # set, this panel REPLACES the input box: ↑/↓ move the highlight, ⏎
        # selects, 1/2/3 jump, esc = the last option.
        def _choice_text():
            c = self._choice
            if not c:
                return ANSI("")
            out = [c["q"], ""] if c.get("q") else [""]
            for i, opt in enumerate(c["options"]):
                if i == c["sel"]:
                    out.append(f"\x1b[38;5;173m❯ {i + 1}. {opt}\x1b[0m")   # highlighted
                else:
                    out.append(f"\x1b[38;5;245m  {i + 1}. {opt}\x1b[0m")
            return ANSI("\n".join(out))

        def _choice_hint():
            return ANSI(" \x1b[38;5;240m↑↓ choose · ⏎ select · 1/2/3 jump · "
                        "esc = last\x1b[0m")

        in_choice = Condition(lambda: self._choice is not None)

        # Claude-Code-style composer: ONLY a top + bottom horizontal rule (no
        # left/right verticals). Completed output streams ABOVE this box (native
        # scrollback); the current partial line sits in `partial_win`.
        def _rule():
            return Window(height=1, char="─", style="class:rule")
        choice_panel = ConditionalContainer(HSplit([
            _rule(),
            Window(FormattedTextControl(_choice_text), dont_extend_height=True,
                   style="class:input"),
            _rule(),
            Window(FormattedTextControl(_choice_hint), height=1),
        ]), filter=in_choice)
        input_panel = ConditionalContainer(HSplit([
            partial_win,                                 # live streaming line
            _rule(),                                     # upper horizontal line
            ta,                                          # input (grows; no side borders)
            _rule(),                                     # bottom horizontal line
            Window(FormattedTextControl(_info), height=1),   # info/status line
        ]), filter=~in_choice)
        body = HSplit([choice_panel, input_panel])

        kb = KeyBindings()
        # Paste-collapse (Claude-Code's `[Pasted text #N +M lines]`); expand on send.
        self._expand = _attach_paste_collapse(ta, kb)

        @kb.add("enter")
        def _(event):
            if self._choice is not None:         # picker mode → confirm selection
                self._choice["result"].put(self._choice["sel"])
                return
            shown = ta.text                      # collapsed (paste placeholders)
            full = self._expand(shown)
            ta.buffer.reset(append_to_history=True)
            if full.strip().lower() in ("/exit", "/quit", "exit", "quit", "q"):
                self._inq.put(None)
                event.app.exit()
                return
            # Echo at SEND time (not when the worker dequeues) so a message typed
            # while the agent is busy appears immediately instead of vanishing.
            if shown.strip():
                self.append(f"\n\x1b[38;5;173m❯\x1b[0m {shown}\n")
            self._inq.put(full)

        @kb.add("escape", "enter")
        def _(event):
            if self._choice is None:
                ta.buffer.insert_text("\n")

        # ↑/↓ move the picker highlight in choice mode; otherwise edit prior
        # messages (auto_up/auto_down move within a multi-line draft, then step
        # through history at the edges — ↑ on an empty prompt recalls the last).
        @kb.add("up")
        def _(event):
            if self._choice is not None:
                self._choice["sel"] = max(0, self._choice["sel"] - 1)
                event.app.invalidate()
                return
            ta.buffer.auto_up(count=event.arg)

        @kb.add("down")
        def _(event):
            if self._choice is not None:
                n = len(self._choice["options"])
                self._choice["sel"] = min(n - 1, self._choice["sel"] + 1)
                event.app.invalidate()
                return
            ta.buffer.auto_down(count=event.arg)

        # 1/2/3 … jump straight to (and confirm) an option while picking.
        for _d in "123456789":
            @kb.add(_d, filter=in_choice)
            def _(event, _d=_d):
                i = int(_d) - 1
                if 0 <= i < len(self._choice["options"]):
                    self._choice["sel"] = i
                    self._choice["result"].put(i)

        @kb.add("escape")
        def _(event):
            if self._choice is not None:         # esc = the last option (No)
                self._choice["result"].put(len(self._choice["options"]) - 1)
                return
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

        style = Style.from_dict({
            "prompt": "fg:#d7875f bold",   # coral ❯ like Claude Code
            "rule": "fg:#d7875f",          # coral top/bottom horizontal lines
            "input": "fg:#ffffff",         # what you type is bright too
        })
        # full_screen=False + patch_stdout = the composer stays PINNED at the
        # bottom while the worker's output scrolls above it in the terminal's
        # native scrollback. mouse_support stays OFF so the terminal (not
        # prompt_toolkit) owns the wheel + click-drag copy, like Claude Code.
        self._app = Application(layout=Layout(body, focused_element=ta),
                                key_bindings=kb, style=style, full_screen=False,
                                refresh_interval=0.2, mouse_support=False)

        _ACTIVE["screen"] = self
        done = {"v": False}

        def _work():
            try:
                worker()
            except (EOFError, KeyboardInterrupt):
                pass                       # normal exit (/exit, Ctrl-C/D)
            except Exception as e:
                self.append(f"\n[tui] worker error: {type(e).__name__}: {e}\n")
            finally:
                done["v"] = True
                app = self._app
                if app is not None:
                    def _safe_exit():
                        # The /exit key handler may have already exited; calling
                        # exit twice raises "Return value already set".
                        try:
                            if app.is_running:
                                app.exit()
                        except Exception:
                            pass
                    try:
                        app.loop.call_soon_threadsafe(_safe_exit)
                    except Exception:
                        pass

        t = threading.Thread(target=_work, daemon=True)
        try:
            # patch_stdout reroutes the worker thread's prints to render ABOVE the
            # live input box instead of corrupting it.
            with patch_stdout(raw=True):
                # Wrap patch_stdout's proxy: only COMPLETE lines reach the
                # scrollback; the in-progress partial line renders in the live
                # region (see _StreamCommit), so token streaming never lands on
                # the box's top rule. Start the worker only after this is set.
                self._stream = _StreamCommit(sys.stdout, self)
                sys.stdout = self._stream
                try:
                    t.start()
                    self._app.run()
                finally:
                    sys.stdout = self._stream._inner
                    self._stream = None
        finally:
            _ACTIVE["screen"] = None
            if not done["v"]:
                self._inq.put(None)              # unblock a waiting worker
            t.join(timeout=3)


def run_full(mode: str, runner) -> bool:
    """Run the REPL with a PERSISTENT two-line composer pinned at the bottom
    (Claude-Code parity: the input box never disappears while the agent works).

    The box is rendered INLINE (no alt-screen) by a prompt_toolkit app on the
    main thread; `runner()` — the REPL loop — runs in a worker thread and its
    output streams ABOVE the box via patch_stdout, into the terminal's native
    scrollback (so wheel-scroll + click-drag copy still work). The worker reads
    input through `tui.read_input`, which is routed to the active screen's queue.

    Returns True when it owns the loop; False to let the caller run the REPL
    directly (no TTY, prompt_toolkit missing, or AI4SCIENCE_TUI=off/box)."""
    if tui_mode() != "full":
        return False
    try:
        import prompt_toolkit  # noqa: F401
        from prompt_toolkit.patch_stdout import patch_stdout  # noqa: F401
    except Exception:
        return False
    try:
        FullScreen(mode).run(runner)
        return True
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        # Any TUI failure → tell the caller to fall back to the plain REPL.
        # (Safe only because read_input below also de-routes once the screen is
        # gone; a failure here means the worker never started consuming input.)
        return False

"""Claude-Code-style input for every agent — a borderless two-line prompt.

The DEFAULT on a real terminal is `full`: a PERSISTENT borderless two-line input
box pinned at the bottom (always visible — type/insert a new message at any time,
Ctrl+C to interrupt the running turn), a live dynamic status (spinner · elapsed ·
tokens · activity), and the agent's output streaming ABOVE it in the terminal's
NATIVE scrollback. Repaint happens only WHILE a turn is busy, so when idle you can
scroll up and it sticks (^G jumps back to the bottom) — like Claude Code.
`AI4SCIENCE_TUI` tunes it: `full` (default), `box`/`1` for a transient per-turn
input (no persistent box), `0`/`off`/`plain` for the classic line-REPL. Uses
prompt_toolkit; falls back to plain input() when off, not a TTY, or pt is absent.

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
_MODE_DISPLAY = {
    "claude-code": "Claude",
    "codex": "Codex",
    "research": "Research",
    "paper": "Paper",
    "unified-LLM": "Unified-LLM",
    "computational-imaging": "Computational Imaging",
}


def _display_mode(mode: str) -> str:
    return _MODE_DISPLAY.get(mode, mode)


# Reverse: a display name (or its lowercase) the user types resolves to the id.
_DISPLAY_TO_ID = {v.lower(): k for k, v in _MODE_DISPLAY.items()}   # {"claude": "claude-code"}


def resolve_mode(name: str) -> str:
    """Map a user-typed agent name to its internal id, so `/agent Claude` (the
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


def _jump_to_bottom(app) -> None:
    """Snap the terminal viewport to the bottom (live composer + newest output).

    With native scrollback (full_screen=False) the terminal owns the scroll
    position, and terminals follow output written at the cursor (the bottom). We
    repaint the composer in place (no `renderer.reset()` — that re-draws WITHOUT
    erasing the old frame and duplicates the box); the emitted redraw bytes land
    at the bottom and pull the viewport down. Safe no-op on any hiccup."""
    try:
        app.invalidate()
    except Exception:
        pass


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
        # Both 'box' (default) and the transient 'full' path use the borderless
        # two-line input: a coral ❯ prompt framed only by top/bottom rules (no
        # left/right box sides), with native wheel-scroll + copy — like Claude Code.
        return _two_line_inline(prompt, mode, status)
    except (EOFError, KeyboardInterrupt):
        raise
    except Exception:
        # any TUI hiccup → never trap the user; fall back to a normal prompt
        return input(prompt)


def _inline_select(question: str, options):
    """Transient inline ↑/↓/⏎ picker (no full-screen, native scrollback kept).
    Returns the 0-based index, or None if cancelled (Esc / Ctrl-C). 1-9 quick-pick."""
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    from prompt_toolkit.formatted_text import ANSI, to_formatted_text

    n = len(options)
    sel = {"i": 0}

    def _frags():
        out = []
        if question:
            # Render the question through ANSI() so embedded colour codes (the
            # syntax-highlighted write/edit preview) show as COLOUR, not raw
            # `^[[…` escape bytes.
            out += list(to_formatted_text(ANSI(question)))
            out.append(("", "\n"))
        for idx, opt in enumerate(options):
            cur = idx == sel["i"]
            out.append(("class:cur" if cur else "",
                        f" {'❯' if cur else ' '} {opt}\n"))
        out.append(("class:hint", " ↑/↓ move · ⏎/Tab select · 1-9 pick · Esc cancel"))
        return out

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")
    def _(e): sel["i"] = (sel["i"] - 1) % n

    @kb.add("down")
    @kb.add("c-n")
    def _(e): sel["i"] = (sel["i"] + 1) % n

    @kb.add("enter")
    @kb.add("tab")
    def _(e): e.app.exit(result=sel["i"])

    @kb.add("escape")
    @kb.add("c-c")
    def _(e): e.app.exit(result=None)

    for _k in range(1, min(n, 9) + 1):
        @kb.add(str(_k))
        def _(e, _k=_k): e.app.exit(result=_k - 1)

    # The question may span multiple lines (e.g. a tool preview) — size the
    # window to fit the whole question + every option + the hint, or options clip.
    q_lines = len(question.splitlines()) if question else 0
    body = HSplit([Window(FormattedTextControl(_frags), height=q_lines + n + 1)])
    style = Style.from_dict({"cur": "fg:#d7875f bold", "q": "bold",
                             "hint": "fg:#8a8a8a"})
    app = Application(layout=Layout(body), key_bindings=kb, style=style,
                     full_screen=False, mouse_support=False, erase_when_done=True)
    return app.run()


def select(question: str, options):
    """Arrow-key picker → 0-based index, or None if cancelled. Uses the
    full-screen picker when a composer owns the terminal, else a transient
    inline picker (box mode), else a numbered text prompt (off / no TTY)."""
    scr = _ACTIVE.get("screen")
    if scr is not None and getattr(scr, "request_choice", None):
        return scr.request_choice(question, options)
    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            import prompt_toolkit  # noqa: F401
            return _inline_select(question, options)
    except Exception:
        pass
    # Non-TTY / no prompt_toolkit: numbered prompt; blank/invalid → None (cancel).
    lines = [question, ""] if question else [""]
    for i, opt in enumerate(options):
        lines.append(f"  {i + 1}. {opt}")
    try:
        ans = (input("\n".join(lines) + "\n❯ ") or "").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    try:
        k = int(ans) - 1
        return k if 0 <= k < len(options) else None
    except ValueError:
        return None


def ask_choice(question: str, options, *, read_input=read_input,
               mode: str = "chat") -> int:
    """Pick one of `options`, returning the 0-based index. Cancel (Esc) resolves
    to the LAST option — the safe 'No' for yes/no confirmations."""
    r = select(question, options)
    return (len(options) - 1) if r is None else r


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

    @kb.add("c-g")                      # jump to bottom (snap to live composer)
    def _(event):
        _jump_to_bottom(event.app)

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

    @kb.add("c-g")                      # jump to bottom (snap to live composer)
    def _(event):
        _jump_to_bottom(event.app)

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

# Playful gerunds for the live status (Claude-Code feel) — one per turn.
_GERUNDS = [
    "Honking", "Simmering", "Noodling", "Percolating", "Pondering", "Brewing",
    "Conjuring", "Churning", "Cooking", "Crunching", "Musing", "Marinating",
    "Vibing", "Wrangling", "Finagling", "Computing", "Spelunking", "Tinkering",
    "Whirring", "Galloping", "Sizzling", "Bubbling", "Concocting", "Schlepping",
]


def begin_turn() -> None:
    """Start the live 'shining' status for a turn (resets elapsed + tokens)."""
    scr = _ACTIVE.get("screen")
    if scr is not None and hasattr(scr, "begin_turn"):
        scr.begin_turn()


def set_tokens(n) -> None:
    """Update the live output-token count shown in the status."""
    scr = _ACTIVE.get("screen")
    if scr is not None and hasattr(scr, "set_tokens"):
        scr.set_tokens(n)


def set_activity(label) -> None:
    """Set what the agent is doing (e.g. 'running grep', 'thinking')."""
    scr = _ACTIVE.get("screen")
    if scr is not None and hasattr(scr, "set_activity"):
        scr.set_activity(label)


def end_turn() -> None:
    scr = _ACTIVE.get("screen")
    if scr is not None and hasattr(scr, "end_turn"):
        scr.end_turn()


def tui_mode() -> str:
    # The full-screen app owns the terminal, so require a real TTY on BOTH
    # ends — `ai4science chat | tee log` must stay a plain pipe-safe REPL.
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return "off"
    v = str(os.environ.get("AI4SCIENCE_TUI", "")).strip().lower()
    if v in ("0", "false", "no", "off", "plain"):
        return "off"
    if v in ("1", "true", "yes", "box"):
        return "box"
    # Default: `full` — the persistent two-line input box (always visible; type /
    # insert a new message at any time, Ctrl+C to interrupt the running turn),
    # with the terminal's native scrollback when idle (no constant repaint). Like
    # Claude Code. `box` is the transient-input fallback (AI4SCIENCE_TUI=box).
    return "full"


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
        self._queued = []               # sent-but-not-yet-processed messages
        self._qlock = threading.Lock()
        # Live "shining" status (Claude-Code style): gerund + elapsed + tokens +
        # what it's doing. Updated by the harness via tui.begin_turn/set_*/end_turn.
        self._turn_t0 = 0.0
        self._tokens = 0
        self._gerund = "Working"
        self._activity = ""

    def begin_turn(self) -> None:
        import time
        try:
            import random
            self._gerund = random.choice(_GERUNDS)
        except Exception:
            self._gerund = "Working"
        self._turn_t0 = time.monotonic()
        self._tokens = 0
        self._activity = "thinking"
        self._invalidate()

    def set_tokens(self, n) -> None:
        try:
            self._tokens = int(n)
        except (TypeError, ValueError):
            return
        self._invalidate()

    def set_activity(self, label) -> None:
        self._activity = label or ""
        self._invalidate()

    def end_turn(self) -> None:
        self._activity = ""
        self._invalidate()

    def _invalidate(self) -> None:
        app = self._app
        if app is not None:
            try:
                app.loop.call_soon_threadsafe(app.invalidate)
            except Exception:
                pass

    def _set_partial(self, s: str) -> None:
        self._partial = s
        # During a turn the busy-ticker already repaints ~7×/s. Invalidating on
        # EVERY streamed token floods the event loop and starves keyboard input
        # (you couldn't type in the box while the agent streamed). So only force a
        # repaint when idle; while busy, let the ticker paint the live region.
        if not self._busy:
            self._invalidate()

    def _queue_msg(self, shown: str) -> None:
        # A message sent while the agent is busy: show it as PENDING just above
        # the composer (stable at the bottom) instead of committing it into the
        # middle of the streaming output. It commits to the transcript only when
        # the worker actually dequeues it (_dequeue_msg), like Claude Code.
        with self._qlock:
            self._queued.append(shown)
        self._invalidate()

    def _dequeue_msg(self):
        with self._qlock:
            shown = self._queued.pop(0) if self._queued else None
        self._invalidate()
        return shown

    def _pull_last_queued(self):
        """Take the most-recently queued (not-yet-processed) message back off BOTH
        the display and the worker input queue, so ↑ can edit it before it runs.
        Returns its shown text, or None if nothing is editably queued."""
        import queue
        with self._qlock:
            if not self._queued:
                return None
            shown = self._queued.pop()               # most recent
            # Drain the worker queue and drop its last real (non-None) item — the
            # message we just pulled, queued in lockstep with the display.
            items = []
            try:
                while True:
                    items.append(self._inq.get_nowait())
            except queue.Empty:
                pass
            for i in range(len(items) - 1, -1, -1):
                if items[i] is not None:
                    del items[i]
                    break
            for it in items:
                self._inq.put(it)
        self._invalidate()
        return shown

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
        # The message was shown as PENDING above the box since SEND time; now
        # that it's actually being processed, move it into the transcript (so it
        # never gets committed into the middle of the previous turn's output).
        shown = self._dequeue_msg()
        echo = shown if shown is not None else line
        if str(echo).strip():
            self.append(f"\n\x1b[38;5;173m❯\x1b[0m {echo}\n")
        return line

    # ── the app ─────────────────────────────────────────────────────────────
    def run(self, worker) -> None:
        """Render the pinned composer on the main thread; `worker()` (no args)
        runs the REPL loop in a background thread, reading input through the
        module-level `read_input` (routed here) and printing output ABOVE the
        box via patch_stdout."""
        # CPR (cursor-position report, ESC[6n) lets prompt_toolkit track the
        # cursor ROW so it can redraw the pinned composer IN PLACE. Forcing it OFF
        # broke that on terminals that DO support CPR: every edit/backspace
        # appended a NEW line instead of overwriting (the corruption + raw ^R/^C
        # echo users hit). Default to leaving CPR ON (prompt_toolkit times out
        # gracefully if the terminal doesn't answer). Terminals that genuinely
        # hang on CPR can still opt out with AI4SCIENCE_NO_CPR=1.
        if os.environ.get("AI4SCIENCE_NO_CPR") == "1":
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
            star = ""
            if self._busy:
                import time
                frame = self._FRAMES[self._frame_i]
                secs = int(time.monotonic() - self._turn_t0) if self._turn_t0 else 0
                toks = self._tokens
                tok_s = f"{toks / 1000:.1f}k" if toks >= 1000 else str(int(toks))
                act = f" · {self._activity}" if self._activity else ""
                # Honking… (29s · ↓ 1.8k tokens · running grep)   — Claude-Code feel
                star = (f"\x1b[38;5;173m{frame} {self._gerund}…\x1b[0m "
                        f"\x1b[38;5;245m({secs}s · ↓ {tok_s} tokens{act} · "
                        f"esc to stop)\x1b[0m  ")
            mode = f"\x1b[38;5;173mai4science · {_display_mode(self.mode)}\x1b[0m"
            extra = (f" · \x1b[38;5;245m{self._status_extra}\x1b[0m"
                     if self._status_extra else "")
            hints = ("   \x1b[38;5;240m⏎ send · ⌥⏎ newline · ↑ edit · ^G bottom · "
                     "/exit\x1b[0m")
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

        # Queued messages: sent while the agent is busy, shown as pending just
        # above the box until the worker processes them (then they move into the
        # transcript). Keeps a just-sent message stable at the bottom instead of
        # scrolling up inside the current turn's output.
        def _queued_text():
            with self._qlock:
                q = list(self._queued)
            if not q:
                return ANSI("")
            return ANSI("\n".join(
                f"\x1b[38;5;173m❯\x1b[0m \x1b[2m{m}  (queued)\x1b[0m" for m in q))

        def _queued_height():
            with self._qlock:
                return len(self._queued)
        queued_win = Window(FormattedTextControl(_queued_text),
                            height=_queued_height, wrap_lines=False,
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
            queued_win,                                  # pending sent messages
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
            # Show the message as PENDING just above the box (stable at the
            # bottom) — it commits to the transcript when the worker processes
            # it, so it never lands in the middle of the current turn's output.
            if shown.strip():
                self._queue_msg(shown)
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
            # ↑ on an empty composer with a pending (queued) message → pull it
            # back into the box to edit before the agent processes it.
            if not ta.text.strip() and self._queued:
                shown = self._pull_last_queued()
                if shown is not None:
                    ta.text = shown
                    ta.buffer.cursor_position = len(shown)
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
            # Ctrl+C while the agent is working → interrupt the running turn
            # (like Esc) and return to the prompt so the user can send a new or
            # steering message — do NOT exit. Only Ctrl+C at the idle prompt
            # exits (Claude Code parity).
            if self._busy:
                from ai4science.harness import interrupt
                interrupt.request()
                self.append("\n\x1b[2m[ctrl-c] interrupting… (type a new message)\x1b[0m\n")
                return
            self._inq.put(None)
            event.app.exit()

        @kb.add("c-d")
        def _(event):
            if not ta.text:
                self._inq.put(None)
                event.app.exit()

        # Ctrl-G — jump to bottom: force a FULL repaint so the terminal snaps its
        # viewport back to the live composer + newest output after you've wheeled
        # up into the scrollback history.
        @kb.add("c-g")
        def _(event):
            _jump_to_bottom(event.app)

        # Ctrl-L — clear the screen + scrollback and repaint a clean composer.
        # Fixes leftover rule lines after a window RESIZE (prompt_toolkit's inline
        # composer re-wraps the scrollback on resize and can't erase the old
        # frame). Like Claude Code's Ctrl-L.
        @kb.add("c-l")
        def _(event):
            try:
                event.app.renderer.clear()
            except Exception:
                pass
            event.app.invalidate()

        style = Style.from_dict({
            "prompt": "fg:#d7875f bold",   # coral ❯ like Claude Code
            "rule": "fg:#d7875f",          # coral top/bottom horizontal lines
            "input": "fg:#ffffff",         # what you type is bright too
        })
        # full_screen=False + patch_stdout = the composer stays PINNED at the
        # bottom while the worker's output scrolls above it in the terminal's
        # native scrollback. mouse_support stays OFF so the terminal (not
        # prompt_toolkit) owns the wheel + click-drag copy, like Claude Code.
        # refresh_interval drives the spinner animation + commits streamed output.
        # (Kept at 0.2 — the known-good value; the refresh_interval=None scroll
        # experiment regressed input, so it was reverted.)
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
    except Exception as e:
        # Any TUI failure → fall back to the plain REPL. SURFACE the reason on
        # stderr (instead of silently degrading to a raw input() with no line
        # editing / no persistent box), and to a debug log, so the cause is
        # diagnosable. Opt in to a full traceback with AI4SCIENCE_TUI_DEBUG=1.
        import sys as _sys, os as _os, traceback as _tb
        print(f"\x1b[33m[tui] persistent input unavailable "
              f"({type(e).__name__}: {e}); using basic input.\x1b[0m", file=_sys.stderr)
        if _os.environ.get("AI4SCIENCE_TUI_DEBUG") == "1":
            _tb.print_exc()
        try:
            _hp = _history_path("_tui_error")
            if _hp is not None:
                _hp.write_text(_tb.format_exc(), encoding="utf-8")
        except Exception:
            pass
        return False

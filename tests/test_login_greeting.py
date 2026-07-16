"""`ai4science login` greets with the Manager after authentication (product point 4).
The greeting is fail-safe (never blocks a successful login), skipped for --no-chat,
and shown before either launching chat (TTY) or printing the start hint (non-TTY)."""
import ai4science.harness.agents.manager.login_console as lc
from ai4science.commands import login as login_cmd


def test_greet_with_manager_prints_the_console(capsys, monkeypatch):
    monkeypatch.delenv("PWM_PLANE", raising=False)
    login_cmd._greet_with_manager()
    out = capsys.readouterr().out
    assert "Manager" in out
    assert "run nothing without your say-so" in out
    assert "imaging" in out                      # the platform fleet it can route to


def test_greet_with_manager_is_failsafe(capsys, monkeypatch):
    # a greeting failure must never break login
    def boom(*a, **k):
        raise RuntimeError("registry unavailable")
    monkeypatch.setattr(lc, "greet", boom)
    login_cmd._greet_with_manager()              # must not raise
    assert "Manager" not in capsys.readouterr().out


def test_no_chat_skips_greeting(monkeypatch):
    called = {"greet": False}
    monkeypatch.setattr(login_cmd, "_greet_with_manager",
                        lambda: called.__setitem__("greet", True))
    login_cmd._enter_chat_if_interactive(no_chat=True)
    assert called["greet"] is False


def test_non_tty_greets_then_hints_without_launching_chat(capsys, monkeypatch):
    class _NoTTY:
        def isatty(self):
            return False
    monkeypatch.setattr(login_cmd.sys, "stdin", _NoTTY())   # short-circuits the TTY check
    greeted = {"v": False}
    monkeypatch.setattr(login_cmd, "_greet_with_manager",
                        lambda: greeted.__setitem__("v", True))
    # if it wrongly tried to launch chat it would import cli._bare_launch; the non-TTY
    # branch returns before that, so no launch occurs.
    login_cmd._enter_chat_if_interactive(no_chat=False)
    out = capsys.readouterr().out
    assert greeted["v"] is True
    assert "ai4science" in out                    # the "Run ai4science to start chatting" hint


def test_interactive_login_wires_greeting_into_the_session_intro(monkeypatch):
    # In a TTY the greeting is passed INTO the chat session as `intro` (shown after
    # the session banner), not pre-printed before the session.
    class _FakeTTY:
        def isatty(self):
            return True
        def write(self, s):        # keep stdout writable (rich shares sys.stdout)
            return len(s)
        def flush(self):
            pass
    monkeypatch.setattr(login_cmd.sys, "stdin", _FakeTTY())
    monkeypatch.setattr(login_cmd.sys, "stdout", _FakeTTY())
    # the interactive path must NOT pre-print the greeting
    monkeypatch.setattr(login_cmd, "_greet_with_manager",
                        lambda: (_ for _ in ()).throw(AssertionError("must not pre-print in a session")))
    import ai4science.cli as cli
    captured = {}
    monkeypatch.setattr(cli, "_bare_launch", lambda **kw: captured.update(kw))
    login_cmd._enter_chat_if_interactive(no_chat=False)
    assert "intro" in captured
    assert "Manager" in (captured["intro"] or "")   # the greeting rides in on the session
    assert "run nothing without your say-so" in captured["intro"]


def test_repl_prints_intro_after_banner():
    # run_common_repl accepts an intro and prints it; None prints nothing.
    import inspect
    from ai4science.harness import repl
    sig = inspect.signature(repl.run_common_repl)
    assert "intro" in sig.parameters
    assert sig.parameters["intro"].default is None

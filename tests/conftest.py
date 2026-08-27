"""Shared test isolation.

The PWM gate now turns ON automatically when an `ai4science login` account is
remembered on disk. Tests must NOT depend on whether the machine running them
happens to be logged in — point the account file at a nonexistent path and
clear the PWM env so the gate is OFF by default. Tests that exercise PWM set
`PWM_TOKEN` / `AI4SCIENCE_PWM_GATE` (and may override the account path)
themselves; monkeypatch applied in the test body wins over this autouse
fixture and restores cleanly.
"""
import os
import signal
import subprocess
import time

import pytest


@pytest.fixture(autouse=True)
def _isolate_pwm_login(monkeypatch, tmp_path_factory):
    missing = tmp_path_factory.mktemp("pwm_isolate") / "no_account.json"
    monkeypatch.setenv("AI4SCIENCE_PWM_ACCOUNT", str(missing))
    for k in ("PWM_TOKEN", "PWM_ONBOARD_TOKEN", "PWM_BASE",
              "PWM_ONBOARD_BASE", "AI4SCIENCE_PWM_GATE"):
        monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture(autouse=True)
def _restore_agent_registry():
    """Put the global agent registry back exactly as it was, for every test.

    Three files carried their own version of this, and all three did it by
    calling `registry.reload()` at teardown — which RE-DISCOVERS through
    whatever `monkeypatch` is still faking. Fixture finalizers run in reverse
    setup order, so when the restore fixture happened to be set up first, its
    teardown ran while `_iter_entry_points` was still patched, and the global
    registry was left holding only the test's fake specs.

    Measured: `test_ai4sci_mode_alias.py` installs a fake spec named `ai4sci`,
    and afterwards `registry.get("research")` returned None for the rest of the
    session — so `ai4science chat --mode research` fell back to the unified
    spec and three tests in `test_chat.py` failed, in a file that passes on its
    own, about a package they never touch.

    Restoring the CONTENTS is order-independent: it needs no discovery, so
    nothing it depends on can still be mocked when it runs.
    """
    from ai4science.harness.agents import registry as _reg
    saved_specs = dict(_reg.AGENT_REGISTRY)
    saved_aliases = dict(_reg.AGENT_ALIASES)
    yield
    if (_reg.AGENT_REGISTRY != saved_specs
            or _reg.AGENT_ALIASES != saved_aliases):
        _reg.AGENT_REGISTRY.clear()
        _reg.AGENT_REGISTRY.update(saved_specs)
        _reg.AGENT_ALIASES.clear()
        _reg.AGENT_ALIASES.update(saved_aliases)


class _SpawnRefused(BaseException):
    """BaseException on purpose — see the fixture below."""


@pytest.fixture(autouse=True)
def _no_real_acp_spawn(monkeypatch):
    """No test may spawn a real ACP bridge. Same doctrine as the fixtures
    above, and a worse failure than either of them.

    `acp.AcpClient.connect` runs `subprocess.Popen` on the real `openclaw acp`
    binary. A test that reaches it starts a genuine gateway bridge — an
    `openclaw` + `openclaw-acp` PAIR — in a pytest tmpdir, and **nothing ever
    stops it**: the client is left in a module-level runtime cache, pytest
    deletes the tmpdir at teardown, and the pair keeps running with its cwd
    pointing at a directory that no longer exists.

    Found by the owner, confirmed by inspection: eighteen orphans across one
    afternoon's runs, every one with a cwd under
    `/tmp/pytest-of-spiritai/garbage-*/test_*/agents/sarsi-worker/work`. They
    accumulate for as long as the suite is run, on any machine that has
    `openclaw` on PATH — which is the machines that matter.

    So the spawn raises here instead. Loudly, and naming the route: a test that
    genuinely means to exercise the spawn machinery injects its own `connect`
    or `wire` (which every `test_acp_*` file already does), and a test that
    reached this by accident gets told which call it was.
    """
    from ai4science.harness.agents.sarsi import acp as _acp

    # Layer 1 — the ordinary path does not spawn.
    #
    # `chat.handle` -> `_new` -> `session.assign` -> `acp.AcpRuntime.start` is
    # production behaviour: filing a directive through the door STARTS a
    # session. A unit test about directive framing therefore reached a real
    # gateway, which is how `test_a_framed_directive_is_filed_with_the_framing_
    # stripped` came to leave an orphan behind it.
    #
    # Stubbed at `start`/`send` rather than at the factory, so
    # `openclaw_acp_runtime` still builds its real argv and a test can still
    # assert on it. The acceptance shape matches the real one: `start` returns
    # an acceptance, never a verdict.
    def fake_start(self, name, cwd, **kw):
        return {"ok": True, "name": name, "pid": -1, "cwd": cwd,
                "acp": True, "stubbed_by": "tests/conftest.py"}

    def fake_send(self, name, text, **kw):
        return {"ok": True, "stubbed_by": "tests/conftest.py"}

    monkeypatch.setattr(_acp.AcpRuntime, "start", fake_start, raising=False)
    monkeypatch.setattr(_acp.AcpRuntime, "send", fake_send, raising=False)

    # Layer 2 — the backstop, and it raises something no `except Exception`
    # can swallow. Production wraps the spawn broadly, so an `AssertionError`
    # here stopped the leak and told nobody: the test passed, and the reason it
    # had reached a gateway at all stayed invisible. That is the exact failure
    # class this suite keeps finding in the code under test, and it should not
    # be reintroduced in the harness that checks it.
    def refuse(self, timeout: float = 30.0):
        raise _SpawnRefused(
            "a test tried to spawn a REAL ACP bridge: "
            f"{' '.join(self._cmd)!r}\n"
            "That starts an openclaw + openclaw-acp pair which outlives the "
            "test and the tmpdir it ran in. Inject a `connect=` or `wire=` "
            "fake, or drive the task with a runtime the test controls.")

    monkeypatch.setattr(_acp.AcpClient, "connect", refuse)

    # Layer 3 — the OTHER spawn. `acp_backend` carries a second runtime class
    # with a second `subprocess.Popen`, reached when `session._rt` resolves a
    # fresh task by BACKEND rather than by an existing session. Layers 1 and 2
    # cover `acp.py` and left this one open: with both in place a run still
    # leaked exactly one pair, which is how it was found. Two spawn sites, two
    # guards — and a count of live processes before and after, because a guard
    # that is merely believed to cover everything is how the first two got
    # written.
    from ai4science.harness.agents.sarsi import acp_backend as _ab

    # Narrowed to the GATEWAY binary. `test_acp_backend` spawns its own peers
    # on purpose — a python script that stalls, one that dies — to prove the
    # deadline fires and that a dead peer reads as errored rather than silent.
    # Those are self-contained, they exit with the test, and refusing them
    # would delete real coverage to fix an unrelated leak. What must not be
    # spawned is `openclaw`: it detaches, outlives the tmpdir, and accumulates.
    _real_stdio_init = _ab.StdioConnection.__init__

    def guarded_stdio(self, command, cwd, *a, **kw):
        if "openclaw" in str(command):
            raise _SpawnRefused(
                f"a test tried to spawn the REAL gateway over stdio: "
                f"{command!r}\n"
                "That pair detaches and outlives the tmpdir. Inject a "
                "`connect=` or `wire=` fake into the runtime.")
        return _real_stdio_init(self, command, cwd, *a, **kw)

    monkeypatch.setattr(_ab.StdioConnection, "__init__", guarded_stdio,
                        raising=False)


def _openclaw_pids():
    """PIDs of openclaw / openclaw-acp processes owned by the current user.

    pgrep rather than a /proc walk so this stays correct if the process names
    gain suffixes; -u limits the blast radius to our own uid, so a shared
    machine's other users are never touched.
    """
    try:
        out = subprocess.run(
            ["pgrep", "-u", str(os.geteuid()), "-x", "openclaw|openclaw-acp"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return {int(line) for line in out.stdout.split() if line.isdigit()}


@pytest.fixture(scope="session", autouse=True)
def _reap_leaked_acp_bridges():
    """Safety net under `_no_real_acp_spawn`: kill any openclaw/openclaw-acp
    pair this session leaves behind.

    The guard above is the primary fix, but it deliberately lets a test opt
    back in by injecting its own `connect=`/`wire=` — which every `test_acp_*`
    file does. Those tests still start real pairs, and the original failure
    mode still applies: the client sits in a module-level runtime cache, pytest
    deletes the tmpdir, and the pair keeps running with a cwd that is gone.

    Measured on agent-prod 2026-08-27 with no such net: 328 orphaned pairs
    holding 8 GB RSS and 29.9 GB of swap, accumulated over three days. Reaping
    them took swap from 232 KB free to 29 GB.

    Deliberately spawn-agnostic — it diffs the openclaw process set across the
    session rather than knowing anything about the client API, so it keeps
    working if that API changes. Session-scoped so it costs two pgrep calls per
    run; per-test was rejected because it would kill bridges belonging to a
    concurrently running suite on the same machine.
    """
    before = _openclaw_pids()
    yield
    leaked = _openclaw_pids() - before
    if not leaked:
        return

    # SIGTERM first so the bridge can close its socket, then SIGKILL. Tearing
    # these down frees their swapped pages, which is real I/O — on an
    # IOPS-constrained host the pause between the two matters.
    for pid in leaked:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not (_openclaw_pids() & leaked):
            break
        time.sleep(0.5)

    for pid in _openclaw_pids() & leaked:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    # Loud on purpose: a silent reaper hides the leak, and the leak is the
    # thing that actually wants fixing.
    pytest.fail(
        f"{len(leaked)} ACP bridge process(es) leaked by this session and were "
        f"reaped: {sorted(leaked)}. A test spawned a real openclaw/openclaw-acp "
        f"pair and did not stop it \u2014 usually one that injected its own "
        f"connect=/wire= and never closed the client. Close it in the test, or "
        f"drive the task with a runtime the test owns.",
        pytrace=False,
    )

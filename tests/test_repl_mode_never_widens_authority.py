"""Invariant 2: entering a mode never widens authority.

The design says a mode is a *lens* — `/sarsi-worker` or `/tsk_…` changes who
the next line is addressed to and nothing else. The machine says something
stronger, and this file pins the stronger thing: on the guided path **there is
no ceiling to widen**. `session.guide` takes no ceiling and no grant parameter
at all, so no mode can raise one, because there is nothing there to raise.

That absence is the invariant. A property phrased as "the same ceiling value
travels down both paths" would be untestable today and would quietly start
passing the day someone threads a ceiling in. Phrased as an absence it turns
red on exactly that refactor — at which point the REPL's guided path has become
a place authority *can* be widened, and this invariant needs re-deciding rather
than re-writing.

Both doors into guidance — the REPL's task mode and `sarsi guide` — reach that
one function with the same four positional arguments and the same `by_owner`
flag. And entering a mode leaves the state tree on disk byte-identical, so
there is no grant or ceiling record for the act of entering to have touched.

Nothing below reaches a model: entering a worker, answering the confirmation
with a bare Enter, and entering a task mode are all decided before any
generation.
"""
import ast
import hashlib
import inspect
import os
import pathlib
import subprocess
import time
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
DOORS = ("ai4science/harness/repl.py", "ai4science/commands/sarsi.py")


def _tree(root):
    return sorted((str(p.relative_to(root)), hashlib.md5(p.read_bytes()).hexdigest())
                  for p in root.rglob("*") if p.is_file())


def _init(state):
    env = {**os.environ, "SARSI_STATE_DIR": str(state), "COLUMNS": "140",
           "TERM": "dumb"}
    init = subprocess.run([sys.executable, "-m", "ai4science.cli", "sarsi",
                           "init", "--owner-id", "7007143162"],
                          capture_output=True, text=True, env=env, timeout=120)
    if init.returncode != 0:
        pytest.skip("cannot init a sarsi registry here")
    return env


def _drive(keys, env):
    """Drive the REAL CLI in a subprocess — which is the point, and the cost.

    Filing a directive through the door starts a session, and on a machine with
    `openclaw` on PATH that is a genuine gateway bridge. The conftest guards
    that stop this in-process cannot reach a child interpreter: it has its own
    Python and never sees a monkeypatch. So a test that drives the CLI for real
    has to clean up after itself, and `_reap_bridges` below is that.
    """
    try:
        p = subprocess.run([sys.executable, "-m", "ai4science.cli", "chat",
                            "--mode", "unified-LLM"], input=keys,
                           capture_output=True, text=True, timeout=150, env=env)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        pytest.skip(f"cannot drive the REPL here: {type(e).__name__}")
    return p.stdout + p.stderr


def _reap_bridges(before):
    """Kill the gateway bridges this test's CLI subprocess left behind.

    By PID, and it has to be. The first attempt drove `sarsi stop` in another
    subprocess, which cannot work by construction: `ses.stop` resolves a
    runtime whose `_clients` cache is empty in a fresh interpreter, finds no
    client for the session name, and no-ops. The bridge is a GRANDCHILD of this
    test — spawned by the CLI child — so nothing in-process holds a handle on
    it and only its pid reaches it.

    Same technique as the session-scoped reaper in `tests/conftest.py`, scoped
    to this test. Both exist on purpose: that one is the backstop for anything
    that slips through, this one keeps the suite green for a test that
    deliberately drives the real CLI and therefore deliberately spawns.
    """
    import signal
    leaked = _openclaw_pids() - before
    for pid in leaked:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and (_openclaw_pids() & leaked):
        time.sleep(0.5)
    for pid in _openclaw_pids() & leaked:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def _openclaw_pids():
    """Live `openclaw` / `openclaw-acp` pids, as a set."""
    try:
        out = subprocess.run(["ps", "-eo", "pid,comm"], capture_output=True,
                             text=True, timeout=20).stdout
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines()[1:]:
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].strip() in ("openclaw", "openclaw-acp"):
            try:
                pids.add(int(parts[0]))
            except ValueError:
                pass
    return pids


def _owner_guide_calls():
    """Every `ses.guide(..., by_owner=True)` call in the two door files.

    Selected by the keyword, never by line number — line numbers move with the
    next edit above them, and a test that pins them fails for the wrong reason.
    Deliberately *not* every `ses.guide` call: `repl.py` also guides on the
    non-owner path with no `by_owner` at all, and that path makes no claim here.
    """
    out = []
    for rel in DOORS:
        tree = ast.parse((REPO / rel).read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if not (isinstance(f, ast.Attribute) and f.attr == "guide"):
                continue
            if not (isinstance(f.value, ast.Name) and
                    f.value.id in ("ses", "session")):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            flag = kw.get("by_owner")
            if isinstance(flag, ast.Constant) and flag.value is True:
                out.append((rel, node.lineno, node.args, set(kw)))
    return out


def test_guide_takes_no_ceiling_or_grant_parameter():
    """The invariant, read straight off the signature.

    If this goes red because a ceiling parameter is being threaded in, the
    REPL's guided path is now a place authority *can* be widened. That is not a
    test to update — it is invariant 2 needing to be re-decided.
    """
    from ai4science.harness.agents.sarsi import session

    params = list(inspect.signature(session.guide).parameters)
    widening = [p for p in params
                if "ceiling" in p.lower() or "grant" in p.lower()]
    assert widening == [], (
        f"session.guide grew {widening}. A ceiling parameter on the guided "
        "path means entering a mode can now widen authority — invariant 2 "
        "needs re-deciding, not this assertion relaxing."
    )
    assert params[:4] == ["config", "agent", "task", "instruction"], params


def test_both_doors_into_guidance_make_the_same_call():
    """Two doors, one call shape — and no third argument sneaking through.

    The REPL's task mode and `sarsi guide` are the owner's two ways in. Each
    passes exactly the four positionals and the owner flag; neither carries
    anything that could name a ceiling.
    """
    calls = _owner_guide_calls()
    assert {rel for rel, _, _, _ in calls} == set(DOORS), (
        f"expected an owner-guided call in each of {DOORS}, found "
        f"{[(r, ln) for r, ln, _, _ in calls]}"
    )
    for rel, lineno, args, kwnames in calls:
        where = f"{rel}:{lineno}"
        assert len(args) == 4, f"{where}: {len(args)} positional args, expected 4"
        assert not any("ceiling" in k.lower() or "grant" in k.lower()
                       for k in kwnames), f"{where}: {sorted(kwnames)}"


def test_entering_a_task_mode_changes_no_grant_or_ceiling_record(tmp_path, request):
    """Entering and leaving a task mode moves no byte on disk.

    The `guided on` assertion carries the same weight as `create it?` in
    `tests/test_repl_entering_costs_nothing.py`: a negative that passes because
    the mode was never entered proves nothing at all.
    """
    state = tmp_path / "state"
    env = _init(state)

    _bridges = _openclaw_pids()
    request.addfinalizer(lambda: _reap_bridges(_bridges))
    made = _drive("/sarsi-worker\nwrite a GAP-TV solver for CASSI\n\n/exit\n", env)

    os.environ["SARSI_STATE_DIR"] = str(state)
    from ai4science.harness.agents.sarsi import registry as reg, task as tsk
    config = reg.load(reg.config_path(state))
    tasks = tsk.all_of(config, config.agents["sarsi-worker"])
    if not tasks:
        pytest.skip(f"no task could be created here: {made[-400:]}")
    tid = tasks[0].id

    before = _tree(state)
    screen = _drive(f"/{tid}\n/back\n/exit\n", env)

    assert "guided on" in screen, screen[-800:]
    assert _tree(state) == before, screen[-800:]

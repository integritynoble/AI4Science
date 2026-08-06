"""A benchmark's generator must run the same code as the harness that spawned it.

`generate_seed` writes the generator into a temp workspace and runs it with
`cwd` set to that workspace. The parent gets `ai4science` on `sys.path` from its
own working directory; the child, started somewhere else, does not — so it falls
back to whatever copy happens to be installed on the machine.

On this machine that copy is **older than `research_agents` existed**, so every
generator that imports the corpus dies with `ModuleNotFoundError` and eight
benchmarks report "generation failed". That is the loud version. The quiet
version is the one worth the test:

    a machine with a merely *stale* install generates its data from old code,
    scores it with new code, and reports a number.

Nothing in the result would say so. This is the same skew that hides records
elsewhere in the system — two ends of one pipeline at different versions — and
the fix is that the child is told, explicitly, where the parent's package lives.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import ai4science
from ai4science.harness.agents.research_agents.runners import common


def _parent_package_root() -> Path:
    """The directory containing the `ai4science` the parent actually imported."""
    return Path(ai4science.__file__).resolve().parent.parent


def test_a_child_process_imports_the_same_ai4science_as_its_parent(tmp_path):
    """Run the real spawn shape — a script in a foreign cwd — and ask it which
    file it imported. Anything but the parent's is a different codebase."""
    ws = tmp_path / "ws"
    (ws / "code").mkdir(parents=True)
    (ws / "code" / "generate.py").write_text(
        "import json, sys, pathlib\n"
        "import ai4science\n"
        "print(json.dumps({'file': str(pathlib.Path(ai4science.__file__).resolve())}))\n"
    )
    out = subprocess.run([sys.executable, "code/generate.py"],
                         cwd=str(ws), capture_output=True, text=True,
                         env=common.child_env())
    assert out.returncode == 0, out.stderr[-2000:]
    got = Path(json.loads(out.stdout)["file"])
    assert got == Path(ai4science.__file__).resolve(), (
        "the generator imported %s while the harness is running %s"
        % (got, Path(ai4science.__file__).resolve()))


def test_the_subpackage_the_generators_actually_need_is_importable(tmp_path):
    """`ModuleNotFoundError: ai4science.harness.agents.research_agents` is the
    failure this machine hits. Importing the top package is not enough — the
    stale install has that and not this."""
    ws = tmp_path / "ws"
    (ws / "code").mkdir(parents=True)
    (ws / "code" / "generate.py").write_text(
        "from ai4science.harness.agents.research_agents.runners import corpus\n"
        "print('ok')\n"
    )
    out = subprocess.run([sys.executable, "code/generate.py"],
                         cwd=str(ws), capture_output=True, text=True,
                         env=common.child_env())
    assert out.returncode == 0, out.stderr[-2000:]


def test_the_env_does_not_discard_what_the_caller_already_set():
    """PYTHONPATH is a list, and a caller who set one meant it. Replacing it
    would make this fix the next version of the bug it repairs."""
    env = common.child_env({"PYTHONPATH": "/somewhere/of/theirs", "X": "1"})
    assert "/somewhere/of/theirs" in env["PYTHONPATH"].split(":")
    assert str(_parent_package_root()) in env["PYTHONPATH"].split(":")
    assert env["X"] == "1"


def test_and_it_does_not_name_the_same_place_twice():
    env = common.child_env({"PYTHONPATH": str(_parent_package_root())})
    assert env["PYTHONPATH"].split(":").count(str(_parent_package_root())) == 1

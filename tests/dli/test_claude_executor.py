"""The Claude Code adapter, and the isolation it must not depend on prompts for.

Most of these run without invoking the CLI: the properties that matter are
about the layout the executor is handed, and a layout can be checked without
spending a model call. The two tests that do call the CLI are skipped when it is
absent, so the suite stays green on a machine without it.

The isolation tests are the important ones. The scripted solvers could not read
the answer key because they had no shell. A real executor has one, and an
executor that can read the answer will eventually read it -- at which point the
benchmark is measuring the directory layout.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from ai4science.harness.agents.delegation.claude_executor import (
    ALLOWED_TOOLS, ClaudeCodeExecutor, available, contract_statement)
from ai4science.harness.agents.delegation.contract import read_task
from ai4science.harness.agents.dli_bench.tasks import GENERATORS

HAVE_CLI, CLI_VERSION = available()
needs_cli = pytest.mark.skipif(not HAVE_CLI,
                               reason="claude CLI not available: %s" % CLI_VERSION)


def test_the_executor_proposes_no_criteria():
    """The thing that will be judged does not write the judgement."""
    ex = ClaudeCodeExecutor()
    c = read_task("t", "do something")
    with tempfile.TemporaryDirectory() as td:
        assert list(ex.propose_criteria(c, Path(td))) == []


def test_the_tool_grant_is_narrow_and_explicit():
    caps = ClaudeCodeExecutor().capabilities()
    assert caps["allowed_tools"] == ALLOWED_TOOLS
    for banned in ("WebFetch", "WebSearch", "Task"):
        assert banned not in ALLOWED_TOOLS


def test_the_isolated_copy_has_no_sibling_to_walk_up_into():
    """`work/` and `keyed/` are siblings in a benchmark instance. The executor
    must never be run somewhere `../keyed` resolves."""
    gen = GENERATORS["t0.csv_to_json"]
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "inst"
        gen.instantiate(root, 0)
        assert (root / "keyed").exists()          # the layout being defended against

        seen = {}

        class Probe(ClaudeCodeExecutor):
            def _run(self, prompt, workspace):
                # `workspace` here is the real one; the sandbox is built inside
                # the real _run. Recreate its shape to inspect it.
                with tempfile.TemporaryDirectory(prefix="cc-exec-") as t2:
                    sandbox = Path(t2) / "task"
                    shutil.copytree(workspace, sandbox)
                    seen["siblings"] = sorted(p.name for p in sandbox.parent.iterdir())
                    seen["parent_has_keyed"] = (sandbox.parent / "keyed").exists()
                return "CONFIDENCE: 0.5", "", 0

        Probe().execute(read_task("t", "x"), root / "work", ())
        assert seen["siblings"] == ["task"], seen
        assert not seen["parent_has_keyed"]


def test_the_key_relocation_removes_it_from_the_tree():
    from ai4science.harness.agents.delegation.live_experiment import _isolate_key
    gen = GENERATORS["t1.clean_dataset"]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        root = td / "inst"
        gen.instantiate(root, 0)
        moved = _isolate_key(root, td / "keys", "arm")
        assert not (root / "keyed").exists()
        assert moved.exists() and any(moved.iterdir())
        # And nothing under the workspace's parent leads back to it.
        assert "keys" not in [p.name for p in root.iterdir()]


def test_the_register_is_not_inside_the_workspace():
    """`store/` holds the criteria and must sit outside the tree the executor
    is given, or the thing being judged can read the judgement."""
    from ai4science.harness.agents.delegation.loop import DelegationAgent
    from ai4science.harness.agents.delegation.bench_solver import CarelessSolver
    gen = GENERATORS["t0.csv_to_json"]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spec = gen.instantiate(td / "i", 0)
        ws, store = td / "i" / "work", td / "i" / "store"
        DelegationAgent(CarelessSolver("t0.csv_to_json"), max_attempts=2).run(
            spec.task_id, spec.prompt, ws, store, class_key="t0.csv_to_json")
        assert (store / "criteria.jsonl").exists()
        assert store not in ws.parents and not str(store).startswith(str(ws) + "/")


def test_self_reported_confidence_is_parsed_and_defaulted_safely():
    ex = ClaudeCodeExecutor()

    class Fixed(ClaudeCodeExecutor):
        def __init__(self, text):
            super().__init__()
            self.text = text

        def _run(self, prompt, workspace):
            return self.text, "", 0

    with tempfile.TemporaryDirectory() as td:
        c = read_task("t", "x")
        assert Fixed("done\nCONFIDENCE: 0.93").execute(c, Path(td), ()).confidence == 0.93
        # No number, and it must not default to certainty.
        assert Fixed("all finished!").execute(c, Path(td), ()).confidence < 1.0


def test_feedback_names_the_failed_checks_and_not_their_contents():
    ex = ClaudeCodeExecutor()
    c = read_task("t", "do the thing")
    with tempfile.TemporaryDirectory() as td:
        p = ex._prompt(c, Path(td), ["these registered checks failed: last_wins"])
        assert "last_wins" in p
        assert "pycode:" not in p and "assert" not in p


def test_the_statement_reaches_the_executor_verbatim():
    c = read_task("t", "Clean raw.csv to the rules in RULES.md")
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "RULES.md").write_text("x", encoding="utf-8")
        s = contract_statement(c, ws)
        assert "Clean raw.csv" in s and "RULES.md" in s


@needs_cli
def test_the_cli_reports_a_version():
    ok, v = available()
    assert ok and "Claude Code" in v


@needs_cli
def test_the_executor_actually_does_a_task_end_to_end():
    """One real call. Slow, and the only way to know the adapter works."""
    gen = GENERATORS["t0.compute_median"]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        spec = gen.instantiate(td / "i", 0)
        keyed = td / "keys"
        shutil.move(str(td / "i" / "keyed"), str(keyed))
        ex = ClaudeCodeExecutor(timeout=420)
        r = ex.execute(read_task(spec.task_id, spec.prompt, td / "i" / "work"),
                       td / "i" / "work", ())
        assert 0.0 <= r.confidence <= 1.0
        assert (td / "i" / "work" / "answer.txt").exists(), (
            "the executor produced no deliverable: %s" % r.note)
        assert gen.verify(td / "i" / "work", keyed).passed

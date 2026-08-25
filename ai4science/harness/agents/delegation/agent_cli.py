"""The command line each level agent binary wraps.

    dl2-agent describe
    dl2-agent run --task ./my_task --statement "clean raw.csv per RULES.md"
    dl2-agent certify

`run` needs a directory holding the inputs. It creates a sibling `.dli-store/`
for the criterion register and the snapshots -- deliberately outside the
workspace, so the thing being judged cannot read the judgement.

The executor defaults to the Claude Code CLI if it is on PATH, and the binary
says so rather than failing obscurely when it is not. Nothing here embeds a
credential: the adapter uses whatever session the CLI already has, which is why
these binaries are safe to hand to someone else.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .bench_solver import COVERED, CarelessSolver
from .claude_executor import ClaudeCodeExecutor, available
from .executor import SolverExecutor
from .levels import SPECS, LevelAgent

BANNER = "DLI level agent -- delegation intelligence, one level per binary"


def _criteria_source(key: Optional[str]):
    """Where acceptance criteria come from when the task is a known class.

    For an arbitrary task there is no derivation rule yet, and the honest
    behaviour is to say so and ask for one rather than invent a check that
    would accept anything.
    """
    if key and key in COVERED:
        return SolverExecutor("criteria", CarelessSolver(key))
    return None


def _executors(model: Optional[str]) -> List:
    ok, why = available()
    if not ok:
        print("no executor: the `claude` CLI is not usable here (%s)." % why,
              file=sys.stderr)
        print("Install Claude Code and sign in, then re-run. This binary "
              "carries no credential of its own.", file=sys.stderr)
        return []
    return [ClaudeCodeExecutor(model=model)]


def cmd_describe(a, level: str) -> int:
    print(BANNER)
    print()
    print(LevelAgent(level, []).describe())
    return 0


def cmd_run(a, level: str) -> int:
    ws = Path(a.task).resolve()
    if not ws.is_dir():
        print("no such task directory: %s" % ws, file=sys.stderr)
        return 2
    store = ws.parent / (".dli-store-" + ws.name)
    ex = _executors(a.model)
    if not ex:
        return 3
    agent = LevelAgent(level, ex, criteria_source=_criteria_source(a.class_key))
    statement = a.statement or _read_statement(ws)
    if not statement:
        print("no statement given and no instruction file found in %s." % ws,
              file=sys.stderr)
        print("Pass --statement, or put a TASK.txt / GOAL.md / SPEC.md there.",
              file=sys.stderr)
        return 2
    out = agent.run(task_id=a.task_id or ws.name, statement=statement,
                    workspace=ws, store=store, band=a.band,
                    class_key=a.class_key)
    print(out.report())
    if a.trace:
        for t in out.trace:
            print("    %s" % t)
    if out.acceptance is not None:
        print()
        print(out.acceptance.report())
    return 0 if out.accepted else 1


def _read_statement(ws: Path) -> str:
    for name in ("TASK.txt", "GOAL.md", "SPEC.md", "QUESTION.txt", "RULES.md"):
        p = ws / name
        if p.exists():
            return p.read_text(encoding="utf-8")[:4000]
    return ""


def cmd_certify(a, level: str) -> int:
    """Run this level against its own band of the benchmark, and report.

    A binary that cannot show what it holds is a label. This is the evidence,
    regenerated on the machine it is run on.
    """
    from .certify import certify
    r = certify(level, seeds=tuple(range(a.seeds)), model=a.model,
                use_claude=not a.offline)
    print(r.report())
    return 0 if r.passed else 1


def build(level: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="%s-agent" % level.lower(),
        description="%s\n\n%s" % (BANNER, SPECS[level].note),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("describe", help="what this level may and may not do")
    d.set_defaults(fn=cmd_describe)

    r = sub.add_parser("run", help="run a task from a directory")
    r.add_argument("--task", required=True, help="directory holding the inputs")
    r.add_argument("--statement", default=None)
    r.add_argument("--task-id", dest="task_id", default=None)
    r.add_argument("--band", default=None,
                   help="difficulty band; the agent refuses above its level")
    r.add_argument("--class-key", dest="class_key", default=None,
                   help="a known benchmark class, so criteria can be derived")
    r.add_argument("--model", default=None)
    r.add_argument("--trace", action="store_true")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("certify", help="run this level against its own band")
    c.add_argument("--seeds", type=int, default=2)
    c.add_argument("--model", default=None)
    c.add_argument("--offline", action="store_true",
                   help="use the scripted executor instead of Claude Code")
    c.set_defaults(fn=cmd_certify)
    return ap


def main(level: str, argv: Optional[Sequence[str]] = None) -> int:
    a = build(level).parse_args(argv)
    return a.fn(a, level)

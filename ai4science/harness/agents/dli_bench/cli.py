"""``python -m ai4science.harness.agents.dli_bench`` -- build, run, score, report.

    dli_bench policy                 the written H0-H5 policy, to hand an evaluator
    dli_bench list                   every generator, and what is not built
    dli_bench build DIR --seeds 0-9  materialise the dataset and its manifest
    dli_bench verify DIR             score one completed instance
    dli_bench demo                   run the reference solvers and print a report
    dli_bench catalog                the 96 specified cards, and which can run
    dli_bench report EPISODES.jsonl  the frontier, from logged episodes
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Sequence

from .dataset import build, write_manifest
from .frontier import cells
from .policy import written_policy
from .report import full_report
from .spec import Episode, Intervention, TaskSpec
from .tasks import COVERAGE, GENERATORS


def _seeds(text: str) -> List[int]:
    out: List[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def cmd_policy(_a) -> int:
    print(written_policy())
    return 0


def cmd_list(_a) -> int:
    print("%-22s %-6s %-9s %-5s %s" % ("generator", "level", "family", "band", "verifier"))
    print("-" * 100)
    for k, g in sorted(GENERATORS.items()):
        print("%-22s %-6s %-9s %-5s %s"
              % (k, g.level, g.family, g.difficulty.band, g.verifier_note[:52]))
    print()
    print("coverage")
    print("-" * 8)
    for lvl, state in COVERAGE.items():
        print("  %-8s %s" % (lvl, state))
    return 0


def cmd_build(a) -> int:
    root = Path(a.directory)
    keys = list(a.only) if a.only else sorted(GENERATORS)
    specs = build(root, keys, _seeds(a.seeds))
    n = write_manifest(specs, root / "manifest.jsonl")
    print("built %d instances from %d generators into %s" % (n, len(keys), root))
    print("manifest: %s" % (root / "manifest.jsonl"))
    print()
    print("Each instance has work/ (given to the agent) and keyed/ (never staged).")
    print("Stage work/ only. An agent that can read keyed/ is grading itself.")
    return 0


def cmd_verify(a) -> int:
    root = Path(a.directory)
    work, keyed = root / "work", root / "keyed"
    if not (work.exists() and keyed.exists()):
        print("%s does not look like an instance: expected work/ and keyed/" % root,
              file=sys.stderr)
        return 2
    key = a.generator or _infer_generator(root)
    if key not in GENERATORS:
        print("cannot tell which generator built this; pass --generator", file=sys.stderr)
        return 2
    v = GENERATORS[key].verify(work, keyed)
    print(v.report())
    return 0 if v.passed else 1


def _infer_generator(root: Path) -> str:
    name = root.parent.name.replace("_", ".", 1)
    return name if name in GENERATORS else ""


def cmd_demo(a) -> int:
    """End to end on the reference solvers.

    This is what the suite looks like when the system under test is correct on
    everything it attempts. It is a harness check, not a result about any
    agent -- the 'system' here is a set of scripted solutions.
    """
    from .reference import SOLVERS
    from datetime import datetime, timedelta, timezone

    keys = list(a.only) if a.only else sorted(GENERATORS)
    seeds = _seeds(a.seeds)
    episodes: List[Episode] = []
    specs: Dict[str, TaskSpec] = {}
    t0 = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        for k in keys:
            g = GENERATORS[k]
            for s in seeds:
                root = td / k.replace(".", "_") / ("seed%d" % s)
                spec = g.instantiate(root, s)
                specs[spec.task_id] = spec
                SOLVERS[k](root / "work", root / "keyed")
                v = g.verify(root / "work", root / "keyed")
                # One governance approval per episode: logged, and it does not
                # lower the level, which is the point of recording the split.
                iv = Intervention(
                    kind="approval", cognitive=False, cid=0,
                    raised_at=t0.isoformat().replace("+00:00", "Z"),
                    responded_at=(t0 + timedelta(seconds=40)).isoformat().replace("+00:00", "Z"),
                    minutes=0.2, note="authorised the write")
                episodes.append(Episode(
                    task_id=spec.task_id, system="reference solvers",
                    budget="H1", band=spec.difficulty.band, family=spec.family,
                    outcome="success" if v.passed else "failure",
                    acceptance_locus="alpha2",
                    verifier_id="dli_bench.verify/%s" % k,
                    interventions=[iv], acceptance_events=1,
                    self_authored_criteria=0,
                    verifier_false_pass_rate=v.false_pass,
                    wall_seconds=1.0))
    print(full_report(episodes, specs, system="reference solvers (harness check)"))
    if a.episodes:
        Path(a.episodes).write_text(
            "\n".join(e.to_json() for e in episodes) + "\n", encoding="utf-8")
        print("\nepisodes written to %s" % a.episodes)
    return 0


def cmd_catalog(a) -> int:
    from .catalog import coverage_report, crosswalk, load
    cards = load()
    if a.runnable_only:
        xw = crosswalk(cards)
        for c in cards:
            if xw[c.task_id]:
                print("%-18s %-8s %-9s -> %s" % (c.task_id, c.level, c.family,
                                                 ", ".join(xw[c.task_id])))
        return 0
    print(coverage_report(cards))
    return 0


def cmd_report(a) -> int:
    eps, specs = [], {}
    for line in Path(a.episodes).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            ivs = [Intervention(**i) for i in d.pop("interventions", [])]
            for k in ("sigma", "max_cid", "t_delta_seconds", "load_seconds"):
                d.pop(k, None)
            eps.append(Episode(interventions=ivs, **d))
    if a.manifest:
        from .spec import Difficulty, Loss
        for line in Path(a.manifest).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            specs[r["task_id"]] = TaskSpec(
                task_id=r["task_id"], family=r["family"], level=r["level"],
                difficulty=Difficulty(**r["difficulty"]), prompt=r["prompt"],
                loss=Loss(value=r["loss"]["value"], c_detect=r["loss"]["c_detect"],
                          c_undo=r["loss"]["c_undo"], c_residual=r["loss"]["c_residual"]),
                verifier_note=r["verifier_note"], seed=r["seed"])
    print(full_report(eps, specs, system=a.system))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="dli_bench", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("policy", help="print the written intervention policy").set_defaults(fn=cmd_policy)
    sub.add_parser("list", help="list generators and coverage").set_defaults(fn=cmd_list)

    b = sub.add_parser("build", help="materialise the dataset")
    b.add_argument("directory")
    b.add_argument("--seeds", default="0-4")
    b.add_argument("--only", nargs="*", default=None)
    b.set_defaults(fn=cmd_build)

    v = sub.add_parser("verify", help="score one completed instance")
    v.add_argument("directory")
    v.add_argument("--generator", default=None)
    v.set_defaults(fn=cmd_verify)

    d = sub.add_parser("demo", help="run the reference solvers and report")
    d.add_argument("--seeds", default="0")
    d.add_argument("--only", nargs="*", default=None)
    d.add_argument("--episodes", default=None, help="also write the episode log here")
    d.set_defaults(fn=cmd_demo)

    c = sub.add_parser("catalog", help="the 96-card catalogue, and what can run it")
    c.add_argument("--runnable-only", action="store_true")
    c.set_defaults(fn=cmd_catalog)

    r = sub.add_parser("report", help="frontier from an episode log")
    r.add_argument("episodes")
    r.add_argument("--manifest", default=None)
    r.add_argument("--system", default="system under test")
    r.set_defaults(fn=cmd_report)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())

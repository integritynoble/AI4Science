#!/usr/bin/env python3
"""Build one standalone binary per delegation level.

    python3 tools/build_level_agents.py --out dist/

Produces `dl0-agent` .. `dl3-agent`: single files, no Python needed on the
target, nothing to install.

What they do NOT contain, deliberately:

  * **no credential of any kind.** The executor adapter shells out to the
    `claude` CLI and uses whatever session that CLI already has. A binary that
    carried a key would be a key you cannot rotate, handed to everyone who
    downloads it.
  * **no answer keys.** Certification regenerates its instances from a seed on
    the machine it runs on, so shipping the binary does not ship the benchmark's
    ground truth.

Each binary can state its own limits (`describe`) and produce its own evidence
(`certify`), which is the point: a level that cannot show what it holds is a
label.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

LEVELS = ("DL0", "DL1", "DL2", "DL3")
ROOT = Path(__file__).resolve().parent.parent

STUB = '''"""Entry point for the %(level)s agent binary. Generated; do not edit."""
import multiprocessing
import sys

from ai4science.harness.agents.delegation.agent_cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main("%(level)s"))
'''

HIDDEN = [
    "ai4science.harness.agents.delegation",
    "ai4science.harness.agents.delegation.agent_cli",
    "ai4science.harness.agents.delegation.certify",
    "ai4science.harness.agents.delegation.levels",
    "ai4science.harness.agents.delegation.bench_solver",
    "ai4science.harness.agents.delegation.claude_executor",
    "ai4science.harness.agents.delegation.dataset_v02",
    "ai4science.harness.agents.dli_bench.tasks",
    "ai4science.harness.agents.dli_bench.tasks.atomic",
    "ai4science.harness.agents.dli_bench.tasks.routine",
    "ai4science.harness.agents.dli_bench.tasks.multistep",
    "ai4science.harness.agents.dli_bench.tasks.sealed",
    "ai4science.harness.agents.dli_bench.envs",
]


def build(level: str, out: Path, pyinstaller: str, work: Path) -> Path:
    stub = work / ("%s_main.py" % level.lower())
    stub.write_text(STUB % {"level": level}, encoding="utf-8")
    name = "%s-agent" % level.lower()
    cmd = [pyinstaller, "--onefile", "--noconfirm", "--clean",
           "--name", name,
           "--distpath", str(out),
           "--workpath", str(work / "build"),
           "--specpath", str(work),
           "--paths", str(ROOT)]
    for h in HIDDEN:
        cmd += ["--hidden-import", h]
    cmd.append(str(stub))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    r = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        sys.stderr.write((r.stdout or "")[-3000:] + (r.stderr or "")[-3000:])
        raise SystemExit("pyinstaller failed for %s" % level)
    return out / name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="dist")
    ap.add_argument("--pyinstaller", default="pyinstaller")
    ap.add_argument("--levels", nargs="*", default=list(LEVELS))
    a = ap.parse_args()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_build"
    work.mkdir(parents=True, exist_ok=True)
    made = []
    for lvl in a.levels:
        p = build(lvl, out, a.pyinstaller, work)
        made.append(p)
        print("built %s (%.1f MB)" % (p, p.stat().st_size / 1e6))
    shutil.rmtree(work, ignore_errors=True)
    print()
    print("These binaries carry no credential. They use the `claude` CLI's")
    print("existing session, so whoever runs one signs in as themselves.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

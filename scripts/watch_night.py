#!/usr/bin/env python3
"""Wait for a long run, and say DEAD instead of waiting on a corpse.

Written after waiting an hour on a night loop that had been killed six minutes
in. The log looked plausible — a header and then nothing — and "nothing yet" is
indistinguishable from "still working" if you only look at the file.

**The reliable signal is the process, not the log.** A night that is killed
stops existing, and that is detectable in seconds without guessing a threshold.
Log staleness is the weaker, secondary signal: a healthy medical-physics round
prints nothing for eleven minutes, so a naive "no output for N minutes means
dead" check would cry wolf on the one agent most likely to need watching.

So this reports three distinct states rather than two, because they need
different responses:

    DONE     the sentinel appeared — the run finished
    DEAD     the process is gone and the sentinel never appeared — it was
             killed, and every further minute of waiting is wasted
    STALLED  the process is alive but the log has not moved in --stale-minutes
             — it may be a long quiet phase, or it may be wedged; this one is a
             prompt to look, not a verdict

Usage:
    python3 scripts/watch_night.py --log /tmp/night.log \\
        --sentinel NIGHT_DONE --pattern night_one.py [--stale-minutes 20]

Exit: 0 done, 2 dead, 3 stalled, 4 timed out.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time


def _alive(pattern: str) -> bool:
    """Is anything matching `pattern` still running?

    pgrep, not a pid: the thing being watched is usually a shell that spawns
    python that spawns solvers, and the pid that was launched is rarely the pid
    doing the work.
    """
    try:
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
    except FileNotFoundError:                     # no pgrep: fall back to log only
        return True
    me = {str(os.getpid()), str(os.getppid())}
    for pid in out.stdout.split():
        if not pid or pid in me:
            continue
        # Exclude this watcher and its shell: the pattern is in OUR argv too, so
        # a naive match finds ourselves and reports the watched run alive
        # forever. That defeats the entire guard — it would sit there saying
        # "still going" about a process that died an hour ago, which is the
        # failure this script exists to stop.
        try:
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmd = f.read().replace(b"\x00", b" ").decode("utf-8", "replace")
        except OSError:
            continue
        if "watch_night" in cmd:
            continue
        return True
    return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", required=True)
    ap.add_argument("--sentinel", default="",
                    help="text whose appearance means finished")
    ap.add_argument("--sentinel-file", default="",
                    help="where the sentinel is written, if not the log. Runs "
                         "often write progress to one file and their exit "
                         "status to another; watching the wrong one makes a "
                         "SUCCESSFUL run look killed, which is the same wrong "
                         "answer in the other direction")
    ap.add_argument("--pattern", default="",
                    help="pgrep pattern for the run; without it, only the log "
                         "is watched and a killed run cannot be told from a "
                         "quiet one")
    ap.add_argument("--stale-minutes", type=float, default=20.0)
    ap.add_argument("--timeout-minutes", type=float, default=180.0)
    ap.add_argument("--poll-seconds", type=float, default=20.0)
    a = ap.parse_args(argv)

    began = time.time()
    last_size, last_change = -1, time.time()
    # A run needs a moment to appear before its absence means anything.
    grace = began + 30.0

    while True:
        text = ""
        try:
            with open(a.log, "r", errors="replace") as f:
                text = f.read()
            size = len(text)
        except FileNotFoundError:
            size = -1
        if size != last_size:
            last_size, last_change = size, time.time()

        done_text = text
        if a.sentinel_file:
            try:
                with open(a.sentinel_file, "r", errors="replace") as f:
                    done_text = f.read()
            except FileNotFoundError:
                done_text = ""
        if a.sentinel and a.sentinel in done_text:
            print("DONE      %s after %.1f min" % (a.log, (time.time() - began) / 60))
            return 0

        if a.pattern and time.time() > grace and not _alive(a.pattern):
            print("DEAD      %s: no process matching %r and the sentinel never "
                  "appeared. Either it was killed — stop waiting — or it "
                  "finished and wrote its sentinel somewhere this is not "
                  "watching (see --sentinel-file). Read the tail before "
                  "concluding. %.1f min."
                  % (a.log, a.pattern, (time.time() - began) / 60), file=sys.stderr)
            tail = "\n".join(text.splitlines()[-8:])
            if tail.strip():
                print("last output:\n%s" % tail, file=sys.stderr)
            return 2

        quiet = (time.time() - last_change) / 60
        if quiet > a.stale_minutes:
            print("STALLED   %s: alive, but the log has not moved in %.1f min. "
                  "Long quiet phases are normal here — look before concluding."
                  % (a.log, quiet), file=sys.stderr)
            return 3

        if (time.time() - began) / 60 > a.timeout_minutes:
            print("TIMEOUT   %s after %.1f min" % (a.log, a.timeout_minutes),
                  file=sys.stderr)
            return 4

        time.sleep(a.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the sarsi live end-to-end tests against a REAL engine, nightly.

WHY THIS EXISTS, stated plainly, because a scheduled job nobody remembers the
purpose of gets deleted the first time it is inconvenient:

The AI4Science suite ran ~4,600 tests green for months while
`sarsi-worker -> sarsi-claude` had NEVER ONCE carried a prompt to a model. The
gateway session came up, spoke ACP correctly, attached to the wrong agent and
sat there. Nothing failed because nothing was asked to exist.

Both live tests are gated behind `SARSI_LIVE_TEST=1`, so they are SKIPPED in
every ordinary run — the tests that prove the capability are excluded from the
number that says the capability is fine. Worse, the spawn guard added on
2026-08-27 means a default run now *cannot* start a real bridge at all. That
guard is right (bridges detach and accumulate: 328 orphans, 29.9 GB of swap),
but it makes the blind spot permanent unless something exercises the real
transport on a schedule. This is that something.

It fails loudly on either of two conditions, and the second is not optional:

  1. a live test failed — the transport or the loop is broken;
  2. an openclaw/openclaw-acp process outlived the run — the leak is back.

Success REMOVES the alert file, so a stale alert can never sit there looking
like a current outage.
"""
import os
import subprocess
import sys
import time

REPO = "/home/spiritai/pwm/Physics_World_Model/AI4Science"
PY_BIN = f"{REPO}/.venv/bin/python"
ALERT = "/home/spiritai/pwm-rescue/ALERT-sarsi-live-gate.md"
FLAKE = "/home/spiritai/pwm-rescue/FLAKE-sarsi-live-gate.md"
TESTS = ["tests/sarsi/test_live_acp_e2e.py", "tests/sarsi/test_live_e2e.py"]
TIMEOUT_S = 1800


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def openclaw_pids():
    """Our own openclaw/openclaw-acp processes.

    `-u` keeps the blast radius to this uid; a shared box's other users are
    never counted and never reported.
    """
    try:
        out = subprocess.run(
            ["pgrep", "-u", str(os.geteuid()), "-x", "openclaw|openclaw-acp"],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None          # unknowable, NOT empty — see write_alert
    return {int(x) for x in out.stdout.split() if x.isdigit()}


def agent_registered():
    """Is there a `sarsi-claude` agent for the bridge to attach to?

    Checked separately so its absence reports as itself. This was the root
    cause of the original stall, and as a test failure it reads like a
    transport bug rather than a machine that needs one command run on it.
    """
    sys.path.insert(0, REPO)
    try:
        from ai4science.harness.agents.sarsi import acp
        known = acp.openclaw_agent_ids()
    except Exception as e:
        return None, f"could not read the openclaw config: {e}"
    if known is None:
        return None, "no readable openclaw config on this machine"
    return ("sarsi-claude" in known), f"configured agents: {', '.join(sorted(known))}"


def write_alert(body):
    os.makedirs(os.path.dirname(ALERT), exist_ok=True)
    with open(ALERT, "w") as fh:
        fh.write(body)
    log(f"wrote {ALERT}")


def clear_alert():
    if os.path.exists(ALERT):
        os.remove(ALERT)
        log(f"cleared {ALERT}")


def main():
    stamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    ok, detail = agent_registered()
    log(f"sarsi-claude registered: {ok} ({detail})")
    if ok is False:
        write_alert(
            f"# ALERT: sarsi-claude is not registered with openclaw\n\n"
            f"Checked {stamp}.\n\n"
            f"The ACP bridge has no agent to attach to, so every delegated "
            f"task will fail at spawn. {detail}\n\n"
            f"Fix:\n\n"
            f"    openclaw agents add sarsi-claude \\\n"
            f"        --workspace ~/.openclaw/workspace-sarsi-claude \\\n"
            f"        --model anthropic/claude-opus-5 --non-interactive\n\n"
            f"Without the `agent:` prefix on the session key this presents as "
            f"an hour of silence on the DEFAULT agent rather than an error, "
            f"which is how it went unnoticed once already.\n")
        return 1

    before = openclaw_pids()
    log(f"openclaw processes before: "
        f"{len(before) if before is not None else 'unknown'}")

    env = {**os.environ, "SARSI_LIVE_TEST": "1"}
    cmd = [PY_BIN, "-m", "pytest", *TESTS, "-q", "-p", "no:randomly"]

    # ONE retry, and the two outcomes are reported differently on purpose.
    #
    # This talks to a live gateway and a live model, so a cold start or a
    # loaded box can time out with nothing wrong: the first run of this gate
    # failed exactly that way and passed on a rerun a minute later. A nightly
    # job that pages for a blip gets muted, and a muted gate is worse than no
    # gate — it reads as coverage while providing none.
    #
    # But a flake that is silently retried away is the same disease in the
    # other direction. So: both attempts failing is an ALERT (broken); a first
    # failure that passes on retry writes a FLAKE note instead — visible,
    # accumulating, and not shaped like an outage.
    out, rc, flaked = "", 0, None
    for attempt in (1, 2):
        log(f"running (attempt {attempt}): {' '.join(cmd)}")
        try:
            run = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True,
                                 text=True, timeout=TIMEOUT_S)
            out, rc = (run.stdout or "") + (run.stderr or ""), run.returncode
        except subprocess.TimeoutExpired:
            out, rc = f"the run did not finish within {TIMEOUT_S}s", 124
        log(f"pytest exit {rc}")
        if rc == 0:
            break
        if attempt == 1:
            flaked = "\n".join(out.strip().splitlines()[-25:])
            log("first attempt failed; retrying once before deciding")

    after = openclaw_pids()
    leaked = (after - before) if (before is not None and after is not None) else set()
    if leaked:
        log(f"LEAKED: {sorted(leaked)}")

    if rc == 0 and not leaked:
        clear_alert()
        if flaked is not None:
            os.makedirs(os.path.dirname(FLAKE), exist_ok=True)
            with open(FLAKE, "a") as fh:
                fh.write(f"\n## {stamp} — failed once, passed on retry\n\n"
                         f"```\n{flaked}\n```\n")
            log(f"appended a flake note to {FLAKE}")
        log("live gate PASSED")
        return 0

    tail = "\n".join(out.strip().splitlines()[-40:])
    reasons = []
    if rc != 0:
        reasons.append(f"the live tests exited {rc}")
    if leaked:
        reasons.append(f"{len(leaked)} openclaw process(es) outlived the run: "
                       f"{sorted(leaked)}")
    write_alert(
        f"# ALERT: the sarsi live gate failed\n\n"
        f"Checked {stamp}. " + "; ".join(reasons) + ".\n\n"
        f"This gate is the ONLY thing that exercises the real ACP transport: "
        f"the live tests are skipped in every ordinary run, and the spawn "
        f"guard means a default run cannot start a bridge at all. A failure "
        f"here means `sarsi-worker -> sarsi-claude` is broken on this machine "
        f"even if the full suite is green.\n\n"
        f"Reproduce:\n\n"
        f"    cd {REPO}\n"
        f"    SARSI_LIVE_TEST=1 .venv/bin/python -m pytest {' '.join(TESTS)} -q\n\n"
        f"Last 40 lines:\n\n```\n{tail}\n```\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())

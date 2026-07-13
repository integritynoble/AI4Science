"""Deterministic citation-grounding checker for the research agent.

Runs inside the A1 sandbox as the registered verify command
(`python3 -I research_check.py --config <json>`), so the control plane
re-runs it and the agent cannot forge the verdict. The trusted config
(report name, source SHA-256s, coverage points) is passed in argv from the
CP-private criteria the sandbox never mounts -- the agent can alter neither
the check parameters nor (via the SHA integrity check) the sources it is
grounded against. Stdlib only; NO ai4science import.

Gates delivery on:
  * integrity -- each source's on-disk SHA-256 matches the config (anti-tamper);
  * format    -- report exists, non-empty, has a `## References` section;
  * citation  -- every substantial body paragraph carries a [S<n>] marker,
                 every marker resolves to a References entry (no dangling);
  * grounding -- each References entry's quoted span appears VERBATIM
                 (whitespace-normalized) in its integrity-verified source;
  * coverage  -- every required coverage point is addressed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

_MARKER = re.compile(r"\[S(\d+)\]")
# References entry: `S<n>: <file> — "<span>"`  (em-dash or hyphen)
_REF = re.compile(r'^S(\d+):\s*(\S+)\s*[—-]\s*"(.+)"\s*$')
_MIN_CLAIM_WORDS = 12


def _norm(text: str) -> str:
    return " ".join(text.split())


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_research(workspace, config: dict) -> dict:
    ws = Path(workspace)
    report_name = config.get("report", "report.md")
    sources = dict(config.get("sources", {}))        # {rel: expected_sha256}
    coverage = list(config.get("coverage_points", []))

    # --- source integrity (anti-tamper): on-disk SHA must match the config ---
    for rel, expected in sources.items():
        try:
            actual = sha256_file(ws / rel)
        except OSError:
            return {"ok": False, "reason": f"integrity: source {rel!r} unreadable"}
        if actual != expected:
            return {"ok": False, "reason": f"integrity: source {rel!r} was tampered with"}

    report_path = ws / report_name
    if not report_path.is_file():
        return {"ok": False, "reason": f"missing report {report_name!r}"}
    report = report_path.read_text()
    if not report.strip():
        return {"ok": False, "reason": "empty report"}
    if "## References" not in report:
        return {"ok": False, "reason": "format: missing '## References' section"}

    body, _, refs_block = report.partition("## References")

    refs: dict = {}
    for line in refs_block.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _REF.match(line)
        if m:
            refs[int(m.group(1))] = (m.group(2), m.group(3))

    # --- citation completeness on the body ---
    for para in re.split(r"\n\s*\n", body):
        p = para.strip()
        if not p or p.startswith("#"):
            continue
        if len(p.split()) < _MIN_CLAIM_WORDS:
            continue
        if not _MARKER.search(p):
            return {"ok": False, "reason": f"citation: uncited claim paragraph: {p[:60]!r}"}

    used = {int(n) for n in _MARKER.findall(body)}
    for n in used:
        if n not in refs:
            return {"ok": False, "reason": f"citation: marker [S{n}] has no References entry"}

    # --- grounding: each used reference's span appears verbatim in its source ---
    source_cache: dict = {}
    for n in used:
        fname, span = refs[n]
        if fname not in sources:
            return {"ok": False, "reason": f"grounding: [S{n}] cites unknown source {fname!r}"}
        if fname not in source_cache:
            try:
                source_cache[fname] = _norm((ws / fname).read_text())
            except OSError:
                return {"ok": False, "reason": f"grounding: source {fname!r} unreadable"}
        if _norm(span) not in source_cache[fname]:
            return {"ok": False,
                    "reason": f"grounding: [S{n}] span not found verbatim in {fname!r}"}

    # --- coverage: every point's significant tokens appear in some single line ---
    report_lines = [_norm(l).lower() for l in report.splitlines() if l.strip()]
    for point in coverage:
        toks = [t for t in re.findall(r"[a-z0-9]+", point.lower()) if len(t) > 3]
        if toks and not any(all(t in line for t in toks) for line in report_lines):
            return {"ok": False, "reason": f"coverage: point not addressed: {point!r}"}

    return {"ok": True, "reason": "grounded"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="JSON: report/source-SHAs/coverage")
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    try:
        config = json.loads(args.config)
    except json.JSONDecodeError:
        sys.stderr.write("invalid --config json\n")
        return 1
    result = check_research(Path(args.workspace), config)
    if not result["ok"]:
        sys.stderr.write(result["reason"] + "\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

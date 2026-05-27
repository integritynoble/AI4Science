"""ai4science overseer — local Founder/AI-Overseer review.

Composition:
  1. run validate (Pydantic + YAML)
  2. run judge if the workspace domain is 'cassi'
  3. compare claims in solution.md with results.json (if available)
  4. flag suspicious patterns (hardcoded absolute paths, missing env
     file, claims without results, modified benchmark files via git)

Outputs:
  reports/overseer_report.json
  reports/overseer_report.md

Final recommendation is one of:
  ACCEPT | REJECT | NEEDS_REVISION | NEEDS_HUMAN_EXPERT_REVIEW | POSSIBLE_SILENT_FAILURE

Hard rule from oversight architecture: this CLI never auto-promotes to
mainnet. The recommendation is advisory; founders multisig signs.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ai4science.judge.cassi import judge_cassi
from ai4science.reports import build_overseer_report
from ai4science.reports.review_report import overseer_report_as_markdown
from ai4science.schemas import SCHEMA_BY_TYPE, parse_front_matter

app = typer.Typer(help="Local Overseer review (validate + judge + claim/suspicion checks).")
console = Console()

NUMERIC_PATTERN = re.compile(r"([-+]?\d+(?:\.\d+)?)(?:\s*(dB|%|))?")


@app.command("review")
def review(
    submission: str = typer.Option(".", "--submission", "-s",
                                    help="Path to the contribution workspace."),
) -> None:
    """Run the full Overseer review."""
    workspace = Path(submission).resolve()
    if not workspace.exists():
        console.print(f"[red]Workspace not found:[/red] {workspace}")
        raise typer.Exit(2)

    reports_dir = workspace / "reports"
    reports_dir.mkdir(exist_ok=True)

    # 1. Validate
    validate_result = _do_validate(workspace)

    # 2. Judge (CASSI-aware)
    judge_report = _maybe_run_judge(workspace)

    # 3. Claims vs results
    claims_check = _check_claims_vs_results(workspace)

    # 4. Suspicions
    suspicions = _scan_suspicions(workspace, judge_report)

    # 5. Recommendation
    recommendation = _decide(validate_result, judge_report, claims_check, suspicions)

    # 6. Persist
    payload = build_overseer_report(
        workspace, validate_result, judge_report, suspicions, claims_check, recommendation,
    )
    (reports_dir / "overseer_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8",
    )
    (reports_dir / "overseer_report.md").write_text(
        overseer_report_as_markdown(payload), encoding="utf-8",
    )

    _render(payload)

    if recommendation in ("REJECT", "POSSIBLE_SILENT_FAILURE"):
        raise typer.Exit(1)


def _do_validate(workspace: Path) -> Dict:
    """Lightweight in-process validation (does not call the validate CLI)."""
    files: Dict[str, Dict[str, str]] = {}
    overall_ok = True
    for fname in ("principle.md", "spec.md", "benchmark.md", "solution.md"):
        path = workspace / fname
        if not path.exists():
            files[fname] = {"status": "absent"}
            continue
        data, err = parse_front_matter(path)
        if err:
            files[fname] = {"status": "broken", "error": err}
            overall_ok = False
            continue
        atype = data.get("artifact_type")
        if atype not in SCHEMA_BY_TYPE:
            files[fname] = {"status": "bad_artifact_type", "error": f"got {atype!r}"}
            overall_ok = False
            continue
        try:
            SCHEMA_BY_TYPE[atype].model_validate(data)
        except ValidationError as e:
            files[fname] = {
                "status": "fail",
                "error": "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
                                   for err in e.errors()),
            }
            overall_ok = False
            continue
        files[fname] = {"status": "ok", "artifact_type": atype}
    return {"ok": overall_ok, "files": files}


def _maybe_run_judge(workspace: Path) -> Dict:
    """Run the CASSI judge if config or benchmark.md indicates the CASSI domain."""
    cfg_path = workspace / ".ai4science" / "config.yaml"
    judge_domain: Optional[str] = None
    if cfg_path.exists():
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            judge_domain = cfg.get("judge_domain")
        except yaml.YAMLError:
            pass

    if judge_domain is None:
        # Fall back: peek at benchmark.md → parent_spec_id includes L2 prefix.
        bench_data, _ = parse_front_matter(workspace / "benchmark.md")
        if bench_data and "CASSI" in str(bench_data.get("name", "")).upper():
            judge_domain = "cassi"

    if judge_domain == "cassi":
        return judge_cassi(workspace)

    return {
        "domain": judge_domain or "unknown",
        "final_decision": "not_run",
        "silent_failure": False,
        "s1_status": "not_run", "s2_status": "not_run",
        "s3_status": "not_run", "s4_status": "not_run",
        "note": "no domain-specific judge available; only generic validation ran",
    }


def _check_claims_vs_results(workspace: Path) -> Dict:
    """Compare numeric claims in solution.md to results/results.json if present."""
    sol_data, sol_err = parse_front_matter(workspace / "solution.md")
    if sol_err or sol_data is None:
        return {
            "claim_count": 0, "results_present": False, "numeric_compared": 0,
            "notes": [f"could not read solution.md: {sol_err}"],
        }
    claims: List[str] = list(sol_data.get("claims", []) or [])

    results_path = workspace / "results" / "results.json"
    results_present = results_path.exists()
    results_data: Dict = {}
    if results_present:
        try:
            results_data = json.loads(results_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return {
                "claim_count": len(claims), "results_present": True,
                "numeric_compared": 0, "notes": [f"results.json malformed: {e}"],
            }

    notes: List[str] = []
    compared = 0
    for claim in claims:
        m = NUMERIC_PATTERN.search(claim)
        if not m:
            continue
        claim_val = float(m.group(1))
        # Look for a matching metric key in results.json (e.g. 'PSNR' / 'psnr').
        for key, observed in results_data.items():
            if key.lower() in claim.lower():
                try:
                    obs_val = float(observed)
                except (TypeError, ValueError):
                    continue
                compared += 1
                rel = abs(obs_val - claim_val) / max(abs(claim_val), 1e-9)
                if rel > 0.10:
                    notes.append(
                        f"claim {claim!r} differs from results {key}={obs_val} by {rel:.1%}"
                    )
                break

    if claims and not results_present:
        notes.append("solution.md has claims but results/results.json is missing")

    return {
        "claim_count": len(claims),
        "results_present": results_present,
        "numeric_compared": compared,
        "notes": notes,
    }


def _scan_suspicions(workspace: Path, judge_report: Dict) -> List[str]:
    """Surface red flags that the deterministic checks don't catch."""
    s: List[str] = []

    # Hardcoded absolute paths in any artifact file?
    abs_path_pat = re.compile(r"(^|\s|=|\"|')(/(?:home|root|Users|var|opt)/[^\s'\"<>)]+)")
    for fname in ("solution.md", "benchmark.md"):
        p = workspace / fname
        if not p.exists():
            continue
        for m in abs_path_pat.finditer(p.read_text(encoding="utf-8")):
            s.append(f"hardcoded absolute path in {fname}: {m.group(2)}")

    # Missing environment file referenced by solution.md
    sol_data, _ = parse_front_matter(workspace / "solution.md")
    if sol_data:
        env_ref = sol_data.get("environment")
        if env_ref:
            env_path = (workspace / env_ref).resolve()
            if not env_path.exists() and not _looks_like_url(env_ref):
                s.append(f"environment file referenced but not found: {env_ref}")

    # Claims without results
    if sol_data:
        claims = list(sol_data.get("claims", []) or [])
        results_present = (workspace / "results" / "results.json").exists()
        if claims and not results_present:
            s.append("solution.md declares claims but results/results.json is missing")

    # git-tracked benchmark / spec files modified (if a git repo)
    if shutil.which("git"):
        try:
            out = subprocess.run(
                ["git", "status", "--porcelain", "benchmark.md", "spec.md"],
                cwd=workspace, capture_output=True, text=True, timeout=5,
            )
            if out.returncode == 0:
                for line in out.stdout.splitlines():
                    if line.strip():
                        s.append(f"git: modified locked artifact: {line.strip()}")
        except Exception:
            pass

    # Judge-side silent failure escalation
    if judge_report.get("silent_failure"):
        s.append("judge detected possible SILENT FAILURE (S1+S3 pass but an S4 check fails)")

    return s


def _looks_like_url(s: str) -> bool:
    return s.startswith(("http://", "https://", "ipfs://", "s3://", "gs://"))


def _decide(validate_result: Dict, judge_report: Dict,
            claims_check: Dict, suspicions: List[str]) -> str:
    if not validate_result["ok"]:
        return "REJECT"
    if judge_report.get("silent_failure"):
        return "POSSIBLE_SILENT_FAILURE"
    if judge_report.get("final_decision") == "fail":
        return "REJECT"
    if judge_report.get("final_decision") == "needs_review":
        return "NEEDS_HUMAN_EXPERT_REVIEW"
    if claims_check.get("notes"):
        return "NEEDS_REVISION"
    if suspicions:
        return "NEEDS_REVISION"
    return "ACCEPT"


def _render(payload: Dict) -> None:
    table = Table(title=f"Overseer Review — {payload['submission_id']}", show_lines=True)
    table.add_column("Section", style="cyan")
    table.add_column("Outcome")
    j = payload["judge"]
    table.add_row("validate", "[green]ok[/green]" if payload["validate"]["ok"] else "[red]fail[/red]")
    table.add_row("judge S1", j["s1_status"])
    table.add_row("judge S2", j["s2_status"])
    table.add_row("judge S3", j["s3_status"])
    table.add_row("judge S4", j["s4_status"])
    table.add_row("silent_failure", str(j["silent_failure"]))
    table.add_row("claims vs results", f"compared {payload['claims_check']['numeric_compared']}; "
                  f"{len(payload['claims_check'].get('notes', []))} notes")
    table.add_row("suspicions", f"{len(payload['suspicions'])} flag(s)")
    table.add_row("[bold]recommendation[/bold]", f"[bold]{payload['recommendation']}[/bold]")
    console.print(table)
    if payload["suspicions"]:
        console.print("\n[yellow]Suspicions:[/yellow]")
        for s in payload["suspicions"]:
            console.print(f"  ⚠ {s}")

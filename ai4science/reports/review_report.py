"""ai4science.reports.review_report — overseer-side report writer."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Dict, List


def build_overseer_report(
    workspace: Path,
    validate_result: Dict,
    judge_report: Dict,
    suspicions: List[str],
    claims_check: Dict,
    recommendation: str,
) -> Dict:
    """Assemble the Overseer report payload that's persisted to reports/."""
    return {
        "schema_version": "0.1",
        "submission_id": workspace.name,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "validate": validate_result,
        "judge": {
            "domain": judge_report.get("domain"),
            "s1_status": judge_report.get("s1_status"),
            "s2_status": judge_report.get("s2_status"),
            "s3_status": judge_report.get("s3_status"),
            "s4_status": judge_report.get("s4_status"),
            "silent_failure": judge_report.get("silent_failure"),
            "final_decision": judge_report.get("final_decision"),
        },
        "suspicions": suspicions,
        "claims_check": claims_check,
        "recommendation": recommendation,
    }


def overseer_report_as_markdown(report: Dict) -> str:
    """Render the report as a human-readable Markdown blob."""
    j = report["judge"]
    cc = report["claims_check"]
    lines = [
        f"# Overseer Report — {report['submission_id']}",
        "",
        f"_Generated: {report['timestamp']}_",
        "",
        f"**Recommendation:** {report['recommendation']}",
        "",
        "## Judge summary",
        "",
        f"| Check | Status |",
        f"|---|---|",
        f"| S1 (finite spec) | {j['s1_status']} |",
        f"| S2 (Hadamard)    | {j['s2_status']} |",
        f"| S3 (benchmark)   | {j['s3_status']} |",
        f"| S4 (overall)     | {j['s4_status']} |",
        f"| Silent failure?  | **{j['silent_failure']}** |",
        f"| Final decision   | **{j['final_decision']}** |",
        "",
        "## Claims vs. results",
        "",
        f"- Claims in solution.md: {cc.get('claim_count', 0)}",
        f"- results.json present: {cc.get('results_present', False)}",
        f"- Numeric claims with results comparison: {cc.get('numeric_compared', 0)}",
    ]
    if cc.get("notes"):
        lines.append("")
        lines.append("### Notes")
        for n in cc["notes"]:
            lines.append(f"- {n}")
    if report["suspicions"]:
        lines.extend(["", "## Suspicions"])
        for s in report["suspicions"]:
            lines.append(f"- ⚠ {s}")
    return "\n".join(lines) + "\n"

"""CASSI judge runner — orchestrates S1-S4 checks and writes judge_report.json."""
from __future__ import annotations

import json
import datetime as dt
from pathlib import Path
from typing import Dict, List

from ai4science.judge import CheckResult
from ai4science.judge.cassi.check_s1 import check_s1
from ai4science.judge.cassi.check_s2 import check_s2
from ai4science.judge.cassi.check_s3 import check_s3
from ai4science.judge.cassi.check_s4_forward_residual import check_s4_forward_residual
from ai4science.judge.cassi.check_s4_noise_consistency import check_s4_noise_consistency
from ai4science.judge.cassi.check_s4_fourier_consistency import check_s4_fourier_consistency
from ai4science.judge.cassi.check_s4_spatial_coherence import check_s4_spatial_coherence


S4_CHECKS = {
    "forward_residual":   check_s4_forward_residual,
    "noise_consistency":  check_s4_noise_consistency,
    "fourier_consistency": check_s4_fourier_consistency,
    "spatial_coherence":  check_s4_spatial_coherence,
}


def judge_cassi(submission: Path) -> Dict:
    """Run all CASSI checks and return a report dict. Also writes reports/judge_report.json."""
    submission = submission.resolve()
    reports_dir = submission / "reports"
    reports_dir.mkdir(exist_ok=True)

    s1 = check_s1(submission)
    s2 = check_s2(submission)
    s3 = check_s3(submission)
    s4_results: Dict[str, CheckResult] = {name: fn(submission) for name, fn in S4_CHECKS.items()}

    # Aggregate S4 status:
    #   any fail → fail
    #   else any pass → pass (warnings tolerated)
    #   else any warning → warning
    #   else → not_available
    s4_statuses = [r.status for r in s4_results.values()]
    if any(s == "fail" for s in s4_statuses):
        s4_aggregate = "fail"
    elif any(s == "pass" for s in s4_statuses):
        s4_aggregate = "pass"
    elif any(s == "warning" for s in s4_statuses):
        s4_aggregate = "warning"
    else:
        s4_aggregate = "not_available"

    # Silent-failure detector: a submission that PASSES S1 + S3 (good paperwork)
    # but FAILS any S4 check is exactly the failure mode the bridge document is
    # about — looks valid on paper, doesn't physically reproduce.
    silent_failure = (
        s1.status == "pass"
        and s3.status == "pass"
        and any(r.status == "fail" for r in s4_results.values())
    )

    # Final decision
    if s1.failed or s3.failed:
        final = "fail"
    elif s4_aggregate == "fail":
        final = "fail"
    elif s4_aggregate == "not_available":
        final = "needs_review"
    elif silent_failure:
        # Defence-in-depth: shouldn't reach here (s4_aggregate would be fail),
        # but if any future change splits the logic, this still surfaces it.
        final = "needs_review"
    else:
        final = "pass"

    # Aggregate warnings / errors lists
    warnings: List[str] = []
    errors: List[str] = []
    for label, r in [("S1", s1), ("S2", s2), ("S3", s3),
                     *[(f"S4_{k}", v) for k, v in s4_results.items()]]:
        if r.status == "warning":
            warnings.append(f"{label}: {r.message}")
        elif r.status == "fail":
            errors.append(f"{label}: {r.message}")
        elif r.status == "not_available":
            warnings.append(f"{label}: {r.message}")

    report = {
        "submission_id": submission.name,
        "domain": "cassi",
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "s1_status": s1.status,
        "s1_message": s1.message,
        "s1_evidence": s1.evidence,
        "s2_status": s2.status,
        "s2_message": s2.message,
        "s2_evidence": s2.evidence,
        "s3_status": s3.status,
        "s3_message": s3.message,
        "s3_evidence": s3.evidence,
        "s4_status": s4_aggregate,
        "s4_checks": {
            name: {"status": r.status, "message": r.message, "evidence": r.evidence}
            for name, r in s4_results.items()
        },
        "silent_failure": silent_failure,
        "warnings": warnings,
        "errors": errors,
        "final_decision": final,
    }

    (reports_dir / "judge_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return report

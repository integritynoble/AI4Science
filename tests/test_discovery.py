"""Tests for content-based artifact discovery (multi-tier support)."""
from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.discovery import (
    discover_artifacts, all_artifact_files, benchmark_files,
    resolve_benchmark, missing_canonical,
)

runner = CliRunner()


def _init(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.chdir(tmp_path)
    r = runner.invoke(app, ["init", "demo"])
    assert r.exit_code == 0, r.output
    return tmp_path / "demo"


T2_FRONT_MATTER = """\
---
artifact_type: benchmark
name: "CASSI T2 Mild Drift"
parent_spec_id: "L2-025-001"
benchmark_id: "L3-025-001-001-T2"
tier: "T2"
dataset_description: |
  T2 drift variant of the T1 scenes.
data_paths:
  - "data/measurement_y_t2.npy"
train_validation_test_split: "5/2/3"
metrics:
  - "PSNR"
physics_checks:
  - "S1"
baseline_methods:
  - "GAP-TV"
success_threshold: "PSNR >= 24.0 dB"
reproducibility_command: "python code/run_t2.py"
---
# T2 body
"""


def test_discover_classifies_by_artifact_type(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    found = discover_artifacts(ws)
    assert [p.name for p in found["principle"]] == ["principle.md"]
    assert [p.name for p in found["spec"]] == ["spec.md"]
    assert [p.name for p in found["benchmark"]] == ["benchmark.md"]
    assert [p.name for p in found["solution"]] == ["solution.md"]


def test_discover_picks_up_extra_benchmark(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    benches = benchmark_files(ws)
    names = [p.name for p in benches]
    assert "benchmark.md" in names
    assert "benchmark_t2.md" in names
    assert len(benches) == 2


def test_discover_sorts_benchmarks_by_name(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    benches = benchmark_files(ws)
    # benchmark.md sorts before benchmark_t2.md
    assert benches[0].name == "benchmark.md"
    assert benches[1].name == "benchmark_t2.md"


def test_discover_ignores_non_artifact_markdown(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "README.md").write_text("# Just docs\n\nNo front matter here.")
    (ws / "NOTES.md").write_text("---\nfoo: bar\n---\n# not an artifact")
    found = discover_artifacts(ws)
    all_names = {p.name for paths in found.values() for p in paths}
    assert "README.md" not in all_names
    assert "NOTES.md" not in all_names


def test_resolve_benchmark_defaults_to_canonical(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    resolved = resolve_benchmark(ws, None)
    assert resolved.name == "benchmark.md"   # canonical preferred


def test_resolve_benchmark_by_name(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    resolved = resolve_benchmark(ws, "benchmark_t2.md")
    assert resolved.name == "benchmark_t2.md"


def test_resolve_benchmark_none_when_empty(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert resolve_benchmark(empty, None) is None


def test_all_artifact_files_ordered(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    files = all_artifact_files(ws)
    types_in_order = []
    from ai4science.schemas import parse_front_matter
    for f in files:
        data, _ = parse_front_matter(f)
        types_in_order.append(data["artifact_type"])
    # principle, spec, then both benchmarks, then solution
    assert types_in_order[0] == "principle"
    assert types_in_order[1] == "spec"
    assert types_in_order.count("benchmark") == 2
    assert types_in_order[-1] == "solution"


def test_missing_canonical_reports_gaps(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ws = tmp_path / "partial"
    ws.mkdir()
    (ws / "principle.md").write_text(
        "---\nartifact_type: principle\nname: x\ndomain: y\n"
        "governing_equation_or_operator: z\ninputs: [a]\noutputs: [b]\n"
        "assumptions: [c]\nvalidity_range: d\nreferences: [e]\n---\n"
    )
    missing = missing_canonical(ws)
    assert "spec.md" in missing
    assert "benchmark.md" in missing
    assert "solution.md" in missing
    assert "principle.md" not in missing


# ─── Multi-benchmark validate + judge integration ────────────────────


def test_validate_picks_up_second_benchmark(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    r = runner.invoke(app, ["validate", "--workspace", str(ws)])
    assert r.exit_code == 0, r.output
    assert "benchmark_t2.md" in r.output


def test_validate_flags_broken_canonical_file(tmp_path, monkeypatch):
    """A spec.md with broken YAML must still be flagged (regression guard):
    discovery skips unparseable files, but validate must surface canonical
    ones that exist-but-don't-classify."""
    ws = _init(tmp_path, monkeypatch)
    (ws / "spec.md").write_text("---\nname: oops\n")   # unterminated front matter
    r = runner.invoke(app, ["validate", "--workspace", str(ws)])
    assert r.exit_code == 1, r.output
    assert "spec.md" in r.output


def test_judge_specific_tier_writes_distinct_report(tmp_path, monkeypatch):
    ws = _init(tmp_path, monkeypatch)
    (ws / "benchmark_t2.md").write_text(T2_FRONT_MATTER)
    from ai4science.judge.cassi import judge_cassi
    report = judge_cassi(ws, benchmark="benchmark_t2.md")
    assert report["benchmark_file"] == "benchmark_t2.md"
    assert (ws / "reports" / "judge_report_benchmark_t2.json").exists()
    # The canonical report name is reserved for benchmark.md
    report_default = judge_cassi(ws)
    assert report_default["benchmark_file"] == "benchmark.md"
    assert (ws / "reports" / "judge_report.json").exists()

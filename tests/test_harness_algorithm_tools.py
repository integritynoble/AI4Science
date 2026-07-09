"""ci-algorithms bundle: science-tier only; base agents are never sub-agents."""
import json

import pytest

from ai4science.harness.agents import registry
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for, dispatchable_targets
from ai4science.harness.agents import capabilities
from ai4science.harness import algorithm_tools

CI_TOOLS = {"ci_modalities", "ci_algorithms", "ci_algorithm_info", "ci_run_algorithm",
            "run_algorithm"}

# The real solver registry lives in the Physics_World_Model monorepo
# (algorithm_base/), outside this package. Tests that hit it can only run
# where that checkout exists (PWM_REPO_ROOT or a parent dir) — e.g. not on a
# bare CI runner.
needs_algorithm_base = pytest.mark.skipif(
    algorithm_tools._repo_root() is None,
    reason="requires the Physics_World_Model checkout (set PWM_REPO_ROOT)")


def test_run_algorithm_preview_and_modality_scope():
    from pathlib import Path
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["run_algorithm"]
    data = Path(algorithm_tools.__file__).parent / "data"
    # preview (confirm omitted) must NOT dispatch — just describe the run + cost
    for m in ("cassi", "mri", "lensless"):
        out = tool.func(".", modality=m)
        assert "[preview]" in out and "confirm=true" in out, m
    # an untuned/unsupported modality is refused with guidance (no dispatch)
    assert "untuned" in tool.func(".", modality="ct")
    # bundled inputs ship with the package
    assert (data / "cassi_ref.npz").exists()
    assert (data / "specs" / "mri.json").exists()
    assert (data / "specs" / "lensless.json").exists()
BASE_AGENTS = {"unified-LLM", "claude-code", "codex"}


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_bundle_resolves(tmp_path):
    tools = capabilities.resolve_capability("ci-algorithms", _ctx(tmp_path))
    assert CI_TOOLS <= {t.name for t in tools}


def test_science_agents_have_ci_tools(tmp_path):
    registry.reload()
    for name in ("research", "paper", "computational-imaging"):
        reg = build_registry_for(registry.get(name), is_subagent=False, ctx=_ctx(tmp_path))
        assert CI_TOOLS <= set(reg.names()), name


def test_open_agents_have_no_ci_tools(tmp_path):
    registry.reload()
    for name in BASE_AGENTS:
        reg = build_registry_for(registry.get(name), is_subagent=False, ctx=_ctx(tmp_path))
        assert not (CI_TOOLS & set(reg.names())), name


def test_base_agents_never_subagents():
    registry.reload()
    for spec in registry.AGENT_REGISTRY.values():
        targets = set(dispatchable_targets(spec))
        assert not (BASE_AGENTS & targets), (spec.name, targets)


@needs_algorithm_base
def test_list_algorithms_real_registry(tmp_path):
    """In-repo: algorithm_base resolves via parent walk; CASSI solvers listed."""
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["ci_algorithms"]
    out = tool.func(tmp_path, modality="cassi")
    assert "GAP-TV" in out and "MST-L" in out


@needs_algorithm_base
def test_modalities_filter(tmp_path):
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["ci_modalities"]
    out = tool.func(tmp_path, filter="cassi")
    assert "cassi" in out


@needs_algorithm_base
def test_info_unknown_solver(tmp_path):
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["ci_algorithm_info"]
    out = tool.func(tmp_path, modality="cassi", solver="nope")
    assert "[ci error]" in out and "nope" in out


@needs_algorithm_base
def test_run_refuses_gpu(tmp_path):
    np = pytest.importorskip("numpy")
    y = tmp_path / "y.npy"
    np.save(y, np.zeros((4, 4)))
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["ci_run_algorithm"]
    out = tool.func(tmp_path, modality="cassi", solver="mst_l", measurement="y.npy")
    assert "[ci error]" in out and "GPU" in out


def test_run_executes_cpu_solver(tmp_path, monkeypatch):
    np = pytest.importorskip("numpy")

    class _Stub:
        @staticmethod
        def list_solvers(modality):
            return [("toy", {"name": "Toy", "gpu": False})]

        @staticmethod
        def run_solver(modality, solver, y, operator, cfg):
            assert cfg == {"iters": 2}
            return y * 2

    monkeypatch.setattr(algorithm_tools, "_algorithm_base", lambda: _Stub)
    np.save(tmp_path / "y.npy", np.ones((3, 3)))
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["ci_run_algorithm"]
    out = tool.func(tmp_path, modality="toy_mod", solver="toy", measurement="y.npy",
                    output="out/x.npy", config=json.dumps({"iters": 2}))
    assert "Toy" in out and "saved" in out
    assert (np.load(tmp_path / "out" / "x.npy") == 2).all()


def test_run_rejects_escaping_path(tmp_path):
    tool = {t.name: t for t in algorithm_tools.algorithm_tools()}["ci_run_algorithm"]
    out = tool.func(tmp_path, modality="cassi", solver="traditional_cpu",
                    measurement="../../etc/passwd")
    assert "[ci error]" in out

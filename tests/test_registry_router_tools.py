# AI4Science/tests/test_registry_router_tools.py
"""science-router agent tools: wrap registry_router, return JSON (network-free)."""
from __future__ import annotations

import json

from ai4science.harness import registry_router_tools as RRT


def _tools(tmp_path):
    return {t.name: t for t in RRT.science_router_tools(gate_provider=None, workspace=tmp_path)}


def test_tools_present_and_readonly(tmp_path):
    tools = _tools(tmp_path)
    assert {"pwm_solve", "pwm_standard_check", "pwm_lineage"} <= set(tools)
    for name in ("pwm_solve", "pwm_standard_check", "pwm_lineage"):
        assert tools[name].mutating is False   # read-only registry lookups


def test_pwm_solve_existing_answer(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.registry_router, "find_problem", lambda q: {
        "query": q, "matched": True, "exists": True,
        "artifact_id": "L3-003", "url": "https://explorer.physicsworldmodel.org/benchmark/L3-003",
        "answer": {"label": "MST-L", "psnr_db": 35.5},
        "lineage": [{"layer": "L1", "artifact_id": "L1-003"}],
        "contribute": False})
    tools = _tools(tmp_path)
    out = json.loads(tools["pwm_solve"].func(str(tmp_path), query="cassi"))
    assert out["exists"] is True
    assert out["answer"]["label"] == "MST-L"
    assert "physicsworldmodel.org" in out["url"]
    assert out["contribute"] is False


def test_pwm_solve_unknown_offers_contribution(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.registry_router, "find_problem", lambda q: {
        "query": q, "matched": False, "exists": False, "answer": None,
        "lineage": [], "contribute": True,
        "contribute_hint": "No matching artifact. Contribute to earn PWM."})
    tools = _tools(tmp_path)
    out = json.loads(tools["pwm_solve"].func(str(tmp_path), query="quantum gravity"))
    assert out["exists"] is False
    assert out["contribute"] is True
    assert "earn" in out["contribute_hint"].lower()


def test_pwm_standard_check(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.registry_router, "standard_check",
                        lambda bid, value, **kw: {
                            "benchmark_id": bid, "value": value,
                            "leaderboard_best": 35.5, "meets_or_beats": value >= 35.5,
                            "reward_eligible": value >= 35.5,
                            "note": "ok" if value >= 35.5 else "BELOW the registry standard"})
    tools = _tools(tmp_path)
    hi = json.loads(tools["pwm_standard_check"].func(str(tmp_path), benchmark_id="L3-003", value=36.0))
    assert hi["meets_or_beats"] is True and hi["reward_eligible"] is True
    lo = json.loads(tools["pwm_standard_check"].func(str(tmp_path), benchmark_id="L3-003", value=30.0))
    assert lo["meets_or_beats"] is False
    assert "below" in lo["note"].lower()


def test_pwm_lineage(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.registry_router, "resolve_lineage", lambda i: [
        {"layer": "L1", "artifact_id": "L1-003", "url": "u1"},
        {"layer": "L2", "artifact_id": "L2-003", "url": "u2"},
        {"layer": "L3", "artifact_id": "L3-003", "url": "u3"}])
    tools = _tools(tmp_path)
    out = json.loads(tools["pwm_lineage"].func(str(tmp_path), artifact_id="L3-003"))
    assert [n["layer"] for n in out["lineage"]] == ["L1", "L2", "L3"]


def test_tool_returns_error_json_on_exception(tmp_path, monkeypatch):
    def _boom(q):
        raise RuntimeError("registry down")
    monkeypatch.setattr(RRT.registry_router, "find_problem", _boom)
    tools = _tools(tmp_path)
    out = json.loads(tools["pwm_solve"].func(str(tmp_path), query="x"))
    assert out["ok"] is False
    assert "registry down" in out["error"]


def test_science_router_capability_bundle_resolves():
    from ai4science.harness.agents.capabilities import resolve_capability, CAPABILITY_BUNDLES
    from ai4science.harness.agents.context import BuildContext
    assert "science-router" in CAPABILITY_BUNDLES
    ctx = BuildContext(workspace=None, brand_provider=None, session_factory=None)
    tools = resolve_capability("science-router", ctx)
    names = {t.name for t in tools}
    assert {"pwm_solve", "pwm_standard_check", "pwm_lineage"} <= names


def test_ci_and_research_specs_have_science_router():
    from ai4science.harness.agents.specs.computational_imaging import AGENT as CI
    # research is now sourced from the pwm-agent-research package via entry
    # point (no local specs/research.py file to import) — fetch it through
    # the registry instead.
    from ai4science.harness.agents import registry
    registry.reload()
    RESEARCH = registry.get("research")
    assert "science-router" in CI.capabilities
    assert "science-router" in RESEARCH.capabilities


def test_pwm_contribute_present_and_mutating(tmp_path):
    tools = {t.name: t for t in RRT.science_router_tools(gate_provider=None, workspace=tmp_path)}
    assert "pwm_contribute" in tools
    assert tools["pwm_contribute"].mutating is True   # economic write -> permission gate


def test_pwm_contribute_requires_login(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.wallet, "platform_token", lambda: None)
    tools = {t.name: t for t in RRT.science_router_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["pwm_contribute"].func(
        str(tmp_path), submission_type="principle", form_data='{"name":"X"}'))
    assert out["ok"] is False
    assert "log in" in out["error"].lower() or "token" in out["error"].lower()


def test_pwm_contribute_submits_and_returns_server_json(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.wallet, "platform_token", lambda: "pwm_testtoken")
    monkeypatch.setattr(RRT.wallet, "platform_base", lambda: "https://physicsworldmodel.org")
    captured = {}
    def _post(base, path, token, body):
        captured.update(base=base, path=path, token=token, body=body)
        return 200, {"success": True, "submission_id": "pwm-pri-abc123",
                     "submission_type": "principle", "status": "testnet",
                     "est_reward": 2.0, "note": "bootstrap"}
    monkeypatch.setattr(RRT.wallet, "http_post", _post)
    tools = {t.name: t for t in RRT.science_router_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["pwm_contribute"].func(
        str(tmp_path), submission_type="principle",
        form_data='{"name":"My Principle","domain":"Imaging"}'))
    assert out["ok"] is True
    assert out["submission_id"] == "pwm-pri-abc123"
    assert out["est_reward"] == 2.0
    # posted to the right endpoint with parsed form_data
    assert captured["path"] == "/api/v1/pwm-submit/self"
    assert captured["token"] == "pwm_testtoken"
    assert captured["body"]["submission_type"] == "principle"
    assert captured["body"]["form_data"]["name"] == "My Principle"


def test_pwm_contribute_bad_form_data_json(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.wallet, "platform_token", lambda: "pwm_testtoken")
    tools = {t.name: t for t in RRT.science_router_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["pwm_contribute"].func(
        str(tmp_path), submission_type="principle", form_data="{not json"))
    assert out["ok"] is False
    assert "form_data" in out["error"].lower()


def test_pwm_contribute_server_error_surfaced(tmp_path, monkeypatch):
    monkeypatch.setattr(RRT.wallet, "platform_token", lambda: "pwm_testtoken")
    monkeypatch.setattr(RRT.wallet, "platform_base", lambda: "https://physicsworldmodel.org")
    monkeypatch.setattr(RRT.wallet, "http_post",
                        lambda *a, **k: (422, {"detail": "submission_type must be one of [...]"}))
    tools = {t.name: t for t in RRT.science_router_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["pwm_contribute"].func(
        str(tmp_path), submission_type="bogus", form_data="{}"))
    assert out["ok"] is False
    assert "422" in out["error"] or "submission_type" in out["error"]

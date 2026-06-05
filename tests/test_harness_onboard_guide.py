from ai4science.harness.onboard_tools import onboard_tools as build


def _tools():
    return {t.name: t for t in build()}


def test_guide_principle(tmp_path):
    out = _tools()["onboard_guide"].func(tmp_path, artifact_type="principle")
    for f in ("name", "domain", "rule", "formula", "reference"):
        assert f in out
    assert "pwm-submit/principle" in out


def test_guide_digital_twin_maps_to_spec(tmp_path):
    out = _tools()["onboard_guide"].func(tmp_path, artifact_type="digital-twin")
    assert "pwm-submit/spec" in out and "operator_type" in out


def test_guide_unknown_type(tmp_path):
    out = _tools()["onboard_guide"].func(tmp_path, artifact_type="nope")
    assert "[onboard error]" in out


def test_guide_tool_non_mutating():
    assert _tools()["onboard_guide"].mutating is False

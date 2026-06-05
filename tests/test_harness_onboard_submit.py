from ai4science.harness import onboard_tools
from ai4science.harness.onboard_tools import onboard_tools as build


def _tools():
    return {t.name: t for t in build()}


_GOOD = {"name": "Energy Conservation", "domain": "mechanics",
         "rule": "energy is conserved", "formula": "dE/dt=0", "reference": "Noether 1918"}


def test_submit_missing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields={"name": "x"})
    assert "[onboard error]" in out and "missing" in out.lower()


def test_submit_no_token(tmp_path, monkeypatch):
    # The actual submit (confirm=True) needs the token...
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD, confirm=True)
    assert "[onboard error]" in out and "PWM_ONBOARD_TOKEN" in out


def test_submit_preview_works_without_token(tmp_path, monkeypatch):
    # ...but the preview is local and must work without a token.
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD)   # confirm omitted
    assert "preview" in out.lower() and "[onboard error]" not in out


def test_submit_preview_no_post(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_post_form",
                        lambda path, fields: (_ for _ in ()).throw(AssertionError("must not POST")))
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD)   # confirm omitted
    assert "preview" in out.lower() and "pwm-submit/principle" in out


def test_submit_string_confirm_does_not_post(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_post_form",
                        lambda path, fields: (_ for _ in ()).throw(AssertionError("must not POST")))
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD, confirm="true")
    assert "preview" in out.lower()


def test_submit_confirm_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    seen = {}
    def fake_post(path, fields):
        seen["path"] = path; seen["fields"] = fields
        return 200, "<div>Submission <b>accepted</b></div>"
    monkeypatch.setattr(onboard_tools, "_post_form", fake_post)
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="digital-twin",
        fields={"principle_id": "P1", "operator_type": "ODE",
                "omega_description": "domain", "epsilon": "0.01", "reference": "ref"},
        confirm=True)
    assert seen["path"] == "/api/v1/pwm-submit/spec"
    assert seen["fields"]["operator_type"] == "ODE"
    assert "submitted" in out.lower() and "accepted" in out.lower()


def test_submit_non_mutating():
    assert _tools()["onboard_submit"].mutating is False

"""Submitting an application — the irreversible one.

`funding` and `jobs` both end here, and this is the act with the longest tail:
you cannot unsubmit an application, and the characteristic failure is a
**plausible** one — well-formed, on time, and wrong in a field nobody read.

So the rules are stricter than mail's or post's:

  * the owner approves **every field and value**, not a prose summary — a form
    is what goes out, so a form is what is shown;
  * an **owner fact** that was inferred rather than supplied stops the
    submission *before* the gate. `jobs` asks rather than invents, and a salary
    expectation nobody stated is exactly the invented answer with the longest
    tail;
  * a required field left empty stops it too — a half-submitted application
    cannot be taken back and completed;
  * reversibility reads **"this cannot be undone"**, never "unknown". For a
    submission, unknown would be a lie of omission.
"""
import pytest

from ai4science.harness.agents.sarsi import (outward, registry as reg, transmit,
                                             vault)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["jobs"]


def _form(**kw):
    fields = kw.pop("fields", None) or [
        transmit.Field("full_name", "Chengshuai Yang", required=True),
        transmit.Field("cover_letter", "I build verifiable agents.", required=True),
        transmit.Field("salary_expectation", "£65,000", required=True, supplied=True),
    ]
    return transmit.Form(url=kw.pop("url", "https://jobs.example/apply"),
                         fields=tuple(fields))


class FakeDriver:
    """Stands in for the browser. `entered` is what it claims it typed."""

    def __init__(self, *, entered=None, fails=False):
        self._entered = entered
        self.fails = fails
        self.calls = []

    def __call__(self, *, url, fields, timeout):
        if self.fails:
            raise RuntimeError("the page never loaded")
        self.calls.append({"url": url, "fields": dict(fields)})
        return dict(self._entered if self._entered is not None else fields)


def _submit(config, agent, driver, form=None):
    return transmit.submit_form(config, agent, form if form is not None else _form(),
                                driver=driver)


# ── the owner sees every field ────────────────────────────────────────

def test_the_form_renders_every_field_and_value(config):
    text = _form().render()
    assert "full_name: Chengshuai Yang" in text
    assert "salary_expectation: £65,000" in text


def test_the_act_body_is_the_form_so_the_gate_shows_it(config, agent):
    act = transmit.submission(agent, _form())
    assert "cover_letter" in outward.render(act)


def test_changing_one_field_changes_the_digest(config, agent):
    a = transmit.submission(agent, _form())
    b = transmit.submission(agent, _form(fields=[
        transmit.Field("full_name", "Someone Else", required=True),
        transmit.Field("cover_letter", "I build verifiable agents.", required=True),
        transmit.Field("salary_expectation", "£65,000", required=True, supplied=True),
    ]))
    assert a.digest() != b.digest()


# ── it cannot be undone, and says so ──────────────────────────────────

def test_a_submission_reads_as_irreversible_never_as_unknown(config, agent):
    act = transmit.submission(agent, _form())
    assert "cannot be undone" in outward.reversibility(act).lower()
    assert "unknown" not in outward.reversibility(act).lower()


# ── owner facts are supplied, never inferred ──────────────────────────

def test_an_inferred_owner_fact_stops_it_before_the_gate(config, agent):
    asked = []
    form = _form(fields=[
        transmit.Field("full_name", "Chengshuai Yang", required=True),
        # inferred: nobody stated this
        transmit.Field("salary_expectation", "£70,000", required=True),
    ])
    driver = FakeDriver()
    with pytest.raises(transmit.AskTheOwnerFirst, match="salary_expectation"):
        outward.request(config, agent, transmit.submission(agent, form),
                        approve=lambda **kw: asked.append(kw) or "yes",
                        transmit=_submit(config, agent, driver, form))
    assert asked == [] and driver.calls == []


def test_a_supplied_owner_fact_is_fine(config, agent):
    driver = FakeDriver()
    out = outward.request(config, agent, transmit.submission(agent, _form()),
                          approve=lambda **kw: "yes",
                          transmit=_submit(config, agent, driver))
    assert out.transmitted is True


def test_an_ordinary_field_may_be_inferred(config, agent):
    form = _form(fields=[transmit.Field("years_experience", "8", required=True)])
    driver = FakeDriver()
    outward.request(config, agent, transmit.submission(agent, form),
                    approve=lambda **kw: "yes",
                    transmit=_submit(config, agent, driver, form))
    assert driver.calls[0]["fields"]["years_experience"] == "8"


# ── a partial application is not submitted ────────────────────────────

def test_a_required_field_left_empty_stops_it(config, agent):
    form = _form(fields=[transmit.Field("full_name", "  ", required=True)])
    driver = FakeDriver()
    with pytest.raises(transmit.IncompleteForm, match="full_name"):
        outward.request(config, agent, transmit.submission(agent, form),
                        approve=lambda **kw: "yes",
                        transmit=_submit(config, agent, driver, form))
    assert driver.calls == []


def test_an_optional_field_may_be_empty(config, agent):
    form = _form(fields=[transmit.Field("full_name", "C. Y.", required=True),
                         transmit.Field("portfolio_url", "")])
    driver = FakeDriver()
    out = outward.request(config, agent, transmit.submission(agent, form),
                          approve=lambda **kw: "yes",
                          transmit=_submit(config, agent, driver, form))
    assert out.transmitted is True


# ── what was actually entered ─────────────────────────────────────────

def test_the_driver_receives_exactly_the_approved_values(config, agent):
    driver = FakeDriver()
    outward.request(config, agent, transmit.submission(agent, _form()),
                    approve=lambda **kw: "yes",
                    transmit=_submit(config, agent, driver))
    assert driver.calls[0]["fields"]["cover_letter"] == "I build verifiable agents."
    assert driver.calls[0]["url"] == "https://jobs.example/apply"


def test_a_driver_that_changed_a_value_is_caught(config, agent):
    """A form that silently trims, re-cases or auto-completes a field has
    submitted something the owner did not read."""
    driver = FakeDriver(entered={"full_name": "CHENGSHUAI YANG",
                                 "cover_letter": "I build verifiable agents.",
                                 "salary_expectation": "£65,000"})
    with pytest.raises(outward.NotWhatWasApproved):
        outward.request(config, agent, transmit.submission(agent, _form()),
                        approve=lambda **kw: "yes",
                        transmit=_submit(config, agent, driver))


def test_a_driver_that_dropped_a_field_is_caught(config, agent):
    """The most dangerous shape: an application that went in missing a field."""
    driver = FakeDriver(entered={"full_name": "Chengshuai Yang",
                                 "salary_expectation": "£65,000"})
    with pytest.raises(outward.NotWhatWasApproved):
        outward.request(config, agent, transmit.submission(agent, _form()),
                        approve=lambda **kw: "yes",
                        transmit=_submit(config, agent, driver))


def test_a_failing_driver_raises_and_is_recorded_as_failed(config, agent):
    from ai4science.harness.agents.sarsi import ledger
    driver = FakeDriver(fails=True)
    with pytest.raises(transmit.TransmitFailed, match="never loaded"):
        outward.request(config, agent, transmit.submission(agent, _form()),
                        approve=lambda **kw: "yes",
                        transmit=_submit(config, agent, driver))
    assert ledger.count(config, "outward", outcome="failed") == 1


# ── who may, and when ─────────────────────────────────────────────────

def test_a_refused_submission_never_reaches_the_driver(config, agent):
    driver = FakeDriver()
    outward.request(config, agent, transmit.submission(agent, _form()),
                    approve=lambda **kw: "no",
                    transmit=_submit(config, agent, driver))
    assert driver.calls == []


def test_a_standing_grant_does_not_cover_submitting(config, agent):
    """`jobs`' own stopping point: asked every time."""
    outward.grant(config, agent_id="jobs", kind="submit", uses=5)
    asked = []
    outward.request(config, agent, transmit.submission(agent, _form()),
                    approve=lambda **kw: asked.append(kw) or "yes",
                    transmit=_submit(config, agent, FakeDriver()))
    assert asked != []


def test_the_real_driver_says_what_it_needs_rather_than_half_working(config, agent):
    """Building it is not the same as having a browser that can drive a site."""
    driver = transmit.playwright_driver(available=lambda: False)
    with pytest.raises(transmit.NoTransmitter, match="playwright"):
        driver(url="https://x", fields={}, timeout=1)

"""The cancer corpus must not consist of the patients who died.

`_tcga_rows` read a living patient's observation time from
`diagnoses.days_to_last_follow_up` alone. GDC populates that field for 17 of 397
living LUAD cases and 259 of 284 living LUSC ones, so the fetcher dropped the
LUAD survivors and kept the deaths: 196 cases, 180 events, a 92% mortality lung
adenocarcinoma cohort. The model was fitted on it and validated on a third of
it, and every check passed, because the only guard was a minimum size.

A cohort that is too small is loud. A cohort that is biased is silent. Both
halves of the fix are tested: read the follow-up time from wherever GDC records
it, and refuse to write a survival cohort with almost no censoring.
"""
from __future__ import annotations

import json

import pytest

from ai4science.harness.agents.research_agents.runners import corpus as _c
from ai4science.harness.agents.research_agents.runners.fetch import runners as R


def _case(sid, *, dead, dtd=None, dx_follow=None, follow_ups=(), age=60.0):
    return {"submitter_id": sid,
            "demographic": {"vital_status": "dead" if dead else "alive",
                            "days_to_death": dtd, "age_at_index": age,
                            "gender": "male"},
            "diagnoses": [{"ajcc_pathologic_stage": "Stage II",
                           "days_to_last_follow_up": dx_follow,
                           "ajcc_pathologic_t": "T2", "ajcc_pathologic_n": "N0",
                           "prior_malignancy": "no"}],
            "follow_ups": [{"days_to_follow_up": d} for d in follow_ups]}


def test_a_living_patient_is_kept_when_only_the_follow_ups_entity_has_the_time():
    """The exact shape of 380 of 397 living LUAD cases: no
    `diagnoses.days_to_last_follow_up`, and a `follow_ups` record that has it."""
    rows = R._tcga_rows([_case("TCGA-01-0001", dead=False, follow_ups=(300, 900))])
    assert len(rows) == 1, "the survivor was dropped"
    assert rows[0]["event"] == 0
    assert rows[0]["time"] == 900, "the LAST visit is the observation time"


def test_both_sources_are_read_and_the_longest_observation_wins():
    """Neither project may ride on the other's recording habits."""
    rows = R._tcga_rows([_case("TCGA-01-0002", dead=False, dx_follow=1200,
                               follow_ups=(300, 900))])
    assert rows[0]["time"] == 1200


def test_a_case_with_no_time_at_all_is_still_dropped():
    """An unknown time is not a long one — the original rule, kept."""
    assert R._tcga_rows([_case("TCGA-01-0003", dead=False)]) == []


def test_a_death_still_uses_the_death_time():
    rows = R._tcga_rows([_case("TCGA-01-0004", dead=True, dtd=500,
                               follow_ups=(9999,))])
    assert rows[0]["event"] == 1 and rows[0]["time"] == 500


def test_an_almost_uncensored_cohort_is_refused(tmp_path, monkeypatch):
    """The guard that the size check could not be. 200 cases is plenty by size
    and 95% deaths is not a cohort."""
    monkeypatch.setattr(_c, "DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(R, "_gdc_cohort", lambda project, size=1200: [
        _case("TCGA-%02d-%04d" % (i % 9, i), dead=i % 20 != 0, dtd=400,
              follow_ups=(400,)) for i in range(200)])
    with pytest.raises(RuntimeError, match="deaths"):
        R.tcga_survival()
    assert not (tmp_path / "tcga-survival" / "dev.json").exists(), (
        "refused and wrote it anyway — everything downstream would still run")


def test_an_ordinary_cohort_is_written(tmp_path, monkeypatch):
    """The guard must not refuse real data: TCGA-LUAD is 36% events."""
    monkeypatch.setattr(_c, "DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(R, "_gdc_cohort", lambda project, size=1200: [
        _case("TCGA-%02d-%04d" % (i % 9, i), dead=i % 3 == 0, dtd=400,
              follow_ups=(400,)) for i in range(200)])
    R.tcga_survival()
    rows = json.loads((tmp_path / "tcga-survival" / "dev.json").read_text())["rows"]
    assert len(rows) == 200
    prov = json.loads((tmp_path / "tcga-survival" / "PROVENANCE.json").read_text())
    assert prov["dev_events"] and prov["dev_events"] < prov["dev_n"], (
        "the event count belongs in provenance — it is what makes the bias "
        "visible without re-deriving it")

from ai4science.harness.agents.work.rsi import run_work_rsi_search, config_id, DEFAULT_WORK_GRID

def _incumbent_default():
    return {"prompt_profile": "terse", "max_steps": 20}

class SearchStub:
    """round_fn stub returning a fixed landscape per domain."""
    def __init__(self, search_ranked, val_ranked):
        self._search = search_ranked
        self._val = val_ranked
        self.calls = []
    def get_last_known_good(self, kind, name):
        return None
    def round(self, *, client, held_out_task_ids, candidates, planner_factory,
              store_factory, domain, **kw):
        self.calls.append((domain, [config_id(c) for c in candidates]))
        table = self._search if domain == "work_search" else self._val
        ranked = sorted(((config_id(c), table.get(config_id(c), (0.0, 0))[0],
                          table.get(config_id(c), (0.0, 0))[1]) for c in candidates),
                        key=lambda x: (-(x[1] or 0.0), x[2]))
        return {"ranked": ranked, "eval_ref": f"ref-{domain}"}

def test_search_picks_best_and_validates(tmp_path):
    # checklist_s20 best on search; validate best vs incumbent(terse_s20) on val
    search = {"terse_s8": (0.4, 6), "terse_s20": (0.6, 9), "checklist_s8": (0.5, 6),
              "checklist_s20": (0.9, 9)}
    val = {"checklist_s20": (0.85, 9), "terse_s20": (0.5, 9)}
    stub = SearchStub(search, val)
    res = run_work_rsi_search(client=stub, planner_factory=lambda c, r, cr: None,
                              store_factory=lambda: None,
                              search_task_ids=[0, 1], val_task_ids=[0, 1],
                              round_fn=stub.round)
    assert config_id(res["best_config"]) == "checklist_s20"
    assert res["search_pass"] == 0.9
    assert res["val_pass"] == 0.85
    assert res["incumbent_val_pass"] == 0.5
    # a search round (all candidates) then a validation round (best + incumbent)
    assert stub.calls[0][0] == "work_search"
    assert stub.calls[-1][0] == "work_val"

def test_rsi_integrity_val_gate_resists_overfit(tmp_path):
    # config A wins search but the incumbent wins val -> val_pass <= incumbent_val_pass
    search = {"checklist_s8": (0.95, 6), "terse_s20": (0.6, 9), "terse_s8": (0.3, 6),
              "checklist_s20": (0.7, 9)}
    val = {"checklist_s8": (0.4, 6), "terse_s20": (0.8, 9)}   # incumbent terse_s20 better on val
    stub = SearchStub(search, val)
    res = run_work_rsi_search(client=stub, planner_factory=lambda c, r, cr: None,
                              store_factory=lambda: None,
                              search_task_ids=[0, 1], val_task_ids=[0, 1],
                              round_fn=stub.round)
    assert config_id(res["best_config"]) == "checklist_s8"          # won the search
    assert res["val_pass"] <= res["incumbent_val_pass"]            # but owner would NOT promote

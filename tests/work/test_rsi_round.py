from ai4science.harness.agents.work.rsi import (config_id, DEFAULT_WORK_GRID,
                                                run_work_rsi_round, ScriptedWorkPlanner)
from ai4science.harness.runtime.task_store import TaskStore

def test_config_id_and_grid():
    assert config_id({"prompt_profile": "terse", "max_steps": 8}) == "terse_s8"
    assert len(DEFAULT_WORK_GRID) == 4
    ids = {config_id(c) for c in DEFAULT_WORK_GRID}
    assert ids == {"terse_s8", "terse_s20", "checklist_s8", "checklist_s20"}

class StubClient:
    """Scores each candidate on each task deterministically: pass iff the
    config's max_steps >= the task's 'difficulty' AND (task even OR profile
    checklist). Records per-(version,task) pass so evaluate_candidates can bind."""
    def __init__(self):
        self.run = 0
        self.scored = {}     # (version, task) -> pass
    def open_run(self, goal, cap, limits, interaction_profile="I2"):
        self.run += 1
        return {"run_id": f"r{self.run}", "workspace_path": "/tmp/x", "limits": limits,
                "capability_profile": cap, "interaction_profile": interaction_profile}
    def stage_worktask(self, run_id, task_id, domain="work_search"):
        self._cur_task = task_id; return {"ok": True}
    def sandbox_execute(self, run_id, command, **kw):
        return {"exit_code": 0, "is_error": False, "stdout": "", "stderr": ""}
    def classify(self, run_id, boundary_kind, *, step_summary="", action_type=None):
        return {"decision": "ACT"}
    def evaluate(self, run_id, domain="cassi"):
        return {"decision": "pass", "feedback": {}}
    def score_worktask(self, run_id, task_id, domain="work_search", version=None):
        cfg = next(c for c in DEFAULT_WORK_GRID if config_id(c) == version)
        difficulty = 10 if task_id % 2 else 5
        ok = cfg["max_steps"] >= difficulty and (task_id % 2 == 0 or cfg["prompt_profile"] == "checklist")
        self.scored[(version, task_id)] = 1.0 if ok else 0.0
        return {"pass": 1.0 if ok else 0.0, "steps": 3}
    def register_version(self, kind, name, version, metadata): return {"ok": True}
    def evaluate_candidates(self, run_id, results, domain="work_search"):
        return {"ok": True, "eval_ref": run_id}

def _planner_factory(cfg):
    return lambda: ScriptedWorkPlanner(cfg)

def test_round_ranks_by_pass_then_steps(tmp_path):
    client = StubClient()
    rr = run_work_rsi_round(client=client, held_out_task_ids=[0, 1],
                            planner_factory=_planner_factory,
                            store_factory=lambda: TaskStore(tmp_path / str(id(object()))))
    # checklist_s20 passes both tasks (task0 even/any, task1 odd needs checklist+steps>=10)
    top_id, top_pass, top_steps = rr["ranked"][0]
    assert top_id == "checklist_s20" and top_pass == 1.0
    # ranking is (-pass, steps); every candidate present
    assert len(rr["ranked"]) == 4
    assert rr["eval_ref"] == "r1"

def test_scripted_planner_produces_artifact_step():
    p = ScriptedWorkPlanner({"prompt_profile": "terse", "max_steps": 8})
    from ai4science.harness.runtime.task_store import TaskState
    from ai4science.harness.runtime.contract import compile_contract
    st = TaskState(task_id="t", contract=compile_contract(objective="o",
                    capability_profile="A1", interaction_mode="I2"))
    step = p.next_step(st)
    assert step.request_verify in (True, False)          # emits a real PlanStep

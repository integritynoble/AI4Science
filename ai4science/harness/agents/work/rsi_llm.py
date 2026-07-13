from __future__ import annotations
from .planner import LLMWorkPlanner, DEFAULT_MODEL
from .rsi import run_work_rsi_search

_EMPTY_CRITERIA = {"verify_commands": [], "required_artifacts": []}


def llm_planner_factory(client, *, model: str = DEFAULT_MODEL):
    """Return a planner_factory(cfg, run_id, criteria) that builds a fresh real
    LLMWorkPlanner per (candidate, task, repeat), threading the candidate's
    prompt_profile and the held-out task's criteria (returned by /stage_worktask)
    into the planner's prompt. Brokered /llm_egress; no agent-side key."""
    def factory(cfg, run_id, criteria):
        return LLMWorkPlanner(client, run_id,
                              criteria=criteria if criteria is not None else dict(_EMPTY_CRITERIA),
                              model=model, prompt_profile=cfg.get("prompt_profile", "terse"))
    return factory


def run_work_rsi_search_llm(*, client, store_factory, search_task_ids, val_task_ids,
                            model: str = DEFAULT_MODEL, repeats: int = 3, **kw) -> dict:
    """Real-LLM RSI search: reuse run_work_rsi_search with the real LLM planner
    factory and N-repeat averaged scoring. Owner-signed promotion unchanged."""
    return run_work_rsi_search(client=client,
                               planner_factory=llm_planner_factory(client, model=model),
                               store_factory=store_factory,
                               search_task_ids=search_task_ids, val_task_ids=val_task_ids,
                               repeats=repeats, **kw)

"""sarsi-worker GUIDES two engines; it is not one of them.

SPEC-ai4science §8:

    sarsi-worker **guides** two engines: **sarsi-claude** to run Claude Code,
    and **sarsi-ai4sci** to run ai4sci inside ai4science.

and [A1]:

    `/sarsi-ai4sci` and `/sarsi-claude` are **not** entry points -- they are
    EXECUTORS, not listed and not entered.

So which executor runs a task is a property of the TASK'S BACKEND, chosen per
task, not a fixed property of the worker. `OPENCLAW_ACP_IDS` mapped
`sarsi-worker -> sarsi-claude`, which pins the brain to ONE engine: a task whose
backend is `sarsi-ai4sci` would be handed to Claude Code instead. The wrong
engine runs the work and the record names an executor the owner did not choose.
"""
from ai4science.harness.agents.sarsi import session as ses, backends as bk


def test_the_executor_comes_from_the_backend_not_the_agent():
    """The whole point: same worker, two different engines."""
    for backend, expected in (("sarsi-claude", "sarsi-claude"),
                              ("sarsi-ai4sci", "sarsi-ai4sci")):
        assert bk.acp_agent_for(bk.resolve(backend)) == expected


def test_the_worker_is_not_itself_an_executor():
    """`sarsi-worker` is not a backend, so it can never BE an engine."""
    assert "sarsi-worker" not in bk.NAMES


def test_executor_id_for_a_task_follows_its_backend():
    """A task on the worker with the ai4sci backend must not resolve to Claude."""
    class T:
        agent_id = "sarsi-worker"
        backend = "sarsi-ai4sci"
        session = None
    assert ses.executor_id_for(T()) == "sarsi-ai4sci"

    class T2(T):
        backend = "sarsi-claude"
    assert ses.executor_id_for(T2()) == "sarsi-claude"

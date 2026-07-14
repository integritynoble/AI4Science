from ai4science.harness.agents.manager.telegram_console import (
    build_proposal, handle_callback, run_console,
)
from ai4science.harness.agents.spec import AgentSpec

SPECS = [
    AgentSpec(name="imaging", tier="science", category="specific", title="Computational Imaging",
              description="cassi reconstruction", keywords=("cassi", "reconstruction")),
]


class FakeExecutor:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, agent, demand):
        self.calls.append((agent, demand))
        return self.result


def test_proposal_button_label_reflects_executable():
    p = build_proposal("reconstruct cassi", SPECS, "n1", executable=True)
    assert "Run imaging (governed)" in p["keyboard"][0][0]["text"]
    p2 = build_proposal("reconstruct cassi", SPECS, "n1", executable=False)
    assert "Route to imaging" in p2["keyboard"][0][0]["text"]


def test_handle_callback_executes_when_executor_present():
    ex = FakeExecutor({"ok": True, "ceiling": "A1", "result": {"status": "done"}})
    pending = {"n1": {"demand": "reconstruct cassi", "agent": "imaging"}}
    reply = handle_callback("run:n1", pending, executor=ex)
    assert "Executed 'imaging'" in reply and ex.calls == [("imaging", "reconstruct cassi")]


def test_handle_callback_surfaces_execution_refusal():
    ex = FakeExecutor({"ok": False, "reason": "foundry agent is not active"})
    pending = {"n1": {"demand": "x", "agent": "imaging"}}
    reply = handle_callback("run:n1", pending, executor=ex)
    assert "Execution refused" in reply and "not active" in reply


def test_handle_callback_records_when_no_executor():
    pending = {"n1": {"demand": "x", "agent": "imaging"}}
    reply = handle_callback("run:n1", pending, executor=None)
    assert "Approved" in reply and "owner-gated" in reply


# --- run_console with an executor (fake telegram) ---------------------------

class FakeTG:
    def __init__(self, batches):
        self.batches = list(batches)
        self.sent = []
    def get_updates(self, token, offset=None):
        return self.batches.pop(0) if self.batches else []
    def send_message(self, token, chat_id, text, keyboard=None):
        self.sent.append(text)
    def answer_callback(self, token, cq_id):
        pass


def test_console_executes_on_route_tap():
    ex = FakeExecutor({"ok": True, "ceiling": "A1", "result": {"status": "done"}})
    tg = FakeTG([
        [{"update_id": 1, "message": {"from": {"id": 7}, "text": "reconstruct cassi", "message_id": 50}}],
        [{"update_id": 2, "callback_query": {"id": "c1", "from": {"id": 7}, "data": "run:50"}}],
    ])
    run_console(token="T", chat_id="7", owner_id="7", specs=SPECS, executor=ex,
                max_rounds=2, tg=tg, sleep=lambda s: None)
    assert ex.calls == [("imaging", "reconstruct cassi")]
    assert "Executed 'imaging'" in tg.sent[-1]

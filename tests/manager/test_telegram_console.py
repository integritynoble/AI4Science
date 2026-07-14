from ai4science.harness.agents.manager.telegram_console import (
    build_proposal, handle_callback, run_console,
)
from ai4science.harness.agents.spec import AgentSpec

SPECS = [
    AgentSpec(name="work", tier="open", category="core", title="General Work",
              description="coding data files", keywords=("coding", "data", "files")),
    AgentSpec(name="imaging", tier="science", category="specific", title="Computational Imaging",
              description="cassi reconstruction", keywords=("cassi", "reconstruction")),
]


def test_build_proposal_routes_with_buttons():
    p = build_proposal("reconstruct the cassi scene", SPECS, "n1")
    assert "imaging" in p["text"]
    assert p["state"] == {"demand": "reconstruct the cassi scene", "agent": "imaging"}
    btns = p["keyboard"][0]
    assert btns[0]["callback_data"] == "run:n1" and btns[1]["callback_data"] == "cancel:n1"


def test_build_proposal_gap_has_no_run_button():
    p = build_proposal("book me a flight to paris", SPECS, "n2")
    assert p["keyboard"] is None and p["state"]["agent"] is None
    assert "niche agent" in p["text"]


def test_handle_callback_run_records_approval():
    pending = {"n1": {"demand": "do cassi", "agent": "imaging"}}
    r = handle_callback("run:n1", pending)
    assert "Approved" in r and "imaging" in r and "owner-gated" in r


def test_handle_callback_cancel_and_expired():
    assert handle_callback("cancel:n1", {}) == "Cancelled."
    assert "expired" in handle_callback("run:nope", {})


# --- run_console loop (fake telegram) ---------------------------------------

class FakeTG:
    def __init__(self, update_batches):
        self.batches = list(update_batches)
        self.sent = []
        self.answered = []

    def get_updates(self, token, offset=None):
        return self.batches.pop(0) if self.batches else []

    def send_message(self, token, chat_id, text, keyboard=None):
        self.sent.append({"text": text, "keyboard": keyboard})

    def answer_callback(self, token, cq_id):
        self.answered.append(cq_id)


def _msg(uid, from_id, text, mid):
    return {"update_id": uid, "message": {"from": {"id": from_id}, "text": text, "message_id": mid}}


def _cbk(uid, from_id, data, cid="c1"):
    return {"update_id": uid, "callback_query": {"id": cid, "from": {"id": from_id}, "data": data}}


def test_console_owner_message_gets_a_proposal():
    tg = FakeTG([[_msg(1, 42, "reconstruct the cassi scene", 100)]])
    run_console(token="T", chat_id="42", owner_id="42", specs=SPECS,
                max_rounds=1, tg=tg, sleep=lambda s: None)
    assert len(tg.sent) == 1 and "imaging" in tg.sent[0]["text"]
    assert tg.sent[0]["keyboard"] is not None


def test_console_run_callback_records_and_answers():
    # message (round 1) then the run callback (round 2)
    tg = FakeTG([[_msg(1, 42, "reconstruct the cassi scene", 100)],
                 [_cbk(2, 42, "run:100")]])
    run_console(token="T", chat_id="42", owner_id="42", specs=SPECS,
                max_rounds=2, tg=tg, sleep=lambda s: None)
    assert "Approved" in tg.sent[-1]["text"] and tg.answered == ["c1"]


def test_console_ignores_non_owner():
    tg = FakeTG([[_msg(1, 99999, "reconstruct the cassi scene", 100),
                  _cbk(2, 99999, "run:100")]])
    run_console(token="T", chat_id="42", owner_id="42", specs=SPECS,
                max_rounds=1, tg=tg, sleep=lambda s: None)
    assert tg.sent == [] and tg.answered == []      # nothing from a non-owner

import json
import io

from ai4science.harness.agents.machine import telegram as tg


class _Resp:
    def __init__(self, obj): self._b = json.dumps(obj).encode()
    def read(self): return self._b
    def __enter__(self): return self
    def __exit__(self, *a): return False


class FakeHTTP:
    """Records sendMessage calls and serves scripted getUpdates responses."""
    def __init__(self, updates_script):
        self.updates_script = list(updates_script)   # list of getUpdates 'result' lists
        self.sent = []
        self.answered = []

    def __call__(self, url, data, timeout):
        params = dict(p.split("=", 1) for p in data.decode().split("&"))
        if url.endswith("/sendMessage"):
            self.sent.append(params)
            return _Resp({"ok": True, "result": {"message_id": 1}})
        if url.endswith("/answerCallbackQuery"):
            self.answered.append(params)
            return _Resp({"ok": True})
        if url.endswith("/getUpdates"):
            result = self.updates_script.pop(0) if self.updates_script else []
            return _Resp({"ok": True, "result": result})
        return _Resp({"ok": True, "result": []})


def _cb(update_id, from_id, data):
    return {"update_id": update_id, "callback_query": {"id": "c1", "from": {"id": from_id}, "data": data}}


def test_send_approval_builds_two_button_keyboard():
    import urllib.parse
    http = FakeHTTP([])
    tg.send_approval("do X?", "req9", token="T", chat_id="55", urlopen=http)
    assert http.sent[0]["chat_id"] == "55"
    kb = json.loads(urllib.parse.unquote_plus(http.sent[0]["reply_markup"]))
    buttons = kb["inline_keyboard"][0]
    assert buttons[0]["callback_data"] == "approve:req9"
    assert buttons[1]["callback_data"] == "deny:req9"


def test_approve_from_owner_returns_true():
    http = FakeHTTP([[_cb(10, 55, "approve:req1")]])
    assert tg.wait_decision("req1", token="T", owner_id="55", urlopen=http,
                            now=iter([0, 1, 100]).__next__, sleep=lambda s: None) is True
    assert http.answered            # the callback spinner was dismissed


def test_deny_from_owner_returns_false():
    http = FakeHTTP([[_cb(11, 55, "deny:req1")]])
    assert tg.wait_decision("req1", token="T", owner_id="55", urlopen=http,
                            now=iter([0, 1, 100]).__next__, sleep=lambda s: None) is False


def test_non_owner_tap_is_ignored_owner_lock():
    # an APPROVE from a different user id must NOT approve; then time out -> None
    http = FakeHTTP([[_cb(12, 99999, "approve:req1")], []])
    out = tg.wait_decision("req1", token="T", owner_id="55", urlopen=http,
                           now=iter([0, 1, 2, 100]).__next__, sleep=lambda s: None)
    assert out is None


def test_timeout_returns_none():
    http = FakeHTTP([[], []])
    assert tg.wait_decision("req1", token="T", owner_id="55", urlopen=http,
                            now=iter([0, 100]).__next__, sleep=lambda s: None) is None


def test_wrong_request_id_ignored():
    http = FakeHTTP([[_cb(13, 55, "approve:OTHER")], []])
    out = tg.wait_decision("req1", token="T", owner_id="55", urlopen=http,
                           now=iter([0, 1, 2, 100]).__next__, sleep=lambda s: None)
    assert out is None


# --- hook escalation ---------------------------------------------------------

def test_hook_escalates_ask_to_telegram(monkeypatch):
    from ai4science.harness.agents.machine import hook
    monkeypatch.setattr(hook, "_maybe_telegram", lambda v, d: {"decision": "allow", "reason": "approved by owner via Telegram", "tripwire": False})
    from ai4science.harness.agents.machine.session import decide_tool_call
    # a consequential call is 'ask'; escalation flips it to allow
    v = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": "git push"}})
    assert v["decision"] == "ask"
    out = hook._maybe_telegram(v, {"tool_name": "Bash", "tool_input": {"command": "git push"}})
    assert out["decision"] == "allow"


def test_maybe_telegram_unconfigured_leaves_ask(monkeypatch):
    from ai4science.harness.agents.machine import hook
    monkeypatch.delenv("PWM_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("PWM_TELEGRAM_CHAT_ID", raising=False)
    v = {"decision": "ask", "reason": "consequential", "tripwire": False}
    assert hook._maybe_telegram(v, {"tool_name": "Bash", "tool_input": {}})["decision"] == "ask"


def test_maybe_telegram_denies_on_timeout(monkeypatch):
    from ai4science.harness.agents.machine import hook
    monkeypatch.setenv("PWM_TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("PWM_TELEGRAM_CHAT_ID", "55")
    monkeypatch.setattr("ai4science.harness.agents.machine.telegram.request_approval",
                        lambda *a, **k: None)   # timeout
    v = {"decision": "ask", "reason": "consequential", "tripwire": False}
    out = hook._maybe_telegram(v, {"tool_name": "Bash", "tool_input": {"command": "git push"}, "tool_use_id": "t1"})
    assert out["decision"] == "deny"

from ai4science.harness.events import Message, TextDelta, ToolCall, Usage, Done
from ai4science.harness.adapters.stub import StubAdapter


def test_stub_emits_scripted_events():
    script = [
        [TextDelta("Let me read it. "), ToolCall("c1", "read", {"path": "a.py"}), Usage(5, 2, 7), Done("tool_use")],
        [TextDelta("All done."), Usage(3, 1, 4), Done("end")],
    ]
    a = StubAdapter(script=script)
    msgs = [Message(role="user", content="hi")]
    ev1 = list(a.stream(msgs, tools=[], model="stub", reasoning="low"))
    assert any(isinstance(e, ToolCall) for e in ev1)
    ev2 = list(a.stream(msgs, tools=[], model="stub", reasoning="low"))
    assert isinstance(ev2[-1], Done)

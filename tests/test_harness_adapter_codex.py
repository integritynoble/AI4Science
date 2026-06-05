import json
from ai4science.harness.adapters.codex import CodexAdapter
from ai4science.harness.adapters import codex_creds
from ai4science.harness.events import (Message, ToolSpec, ToolCall, TextDelta,
                                       Usage, Done, ImagePart)


def test_translate_tools_to_responses_function():
    a = CodexAdapter()
    out = a._translate_tools([ToolSpec("bash", "run a command",
                                       {"type": "object", "properties": {"cmd": {"type": "string"}}})])
    assert out[0]["type"] == "function"
    assert out[0]["name"] == "bash" and out[0]["description"] == "run a command"
    assert out[0]["parameters"]["properties"]["cmd"]["type"] == "string"


def test_translate_input_system_user_assistant_tool():
    a = CodexAdapter()
    msgs = [
        Message(role="system", content="be brief"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "bash", {"cmd": "ls"})]),
        Message(role="tool", content="a.py", tool_call_id="c1"),
    ]
    instr, items = a._translate_input(msgs)
    assert instr == "be brief"
    assert items[0] == {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "hi"}]}
    fc = items[1]
    assert fc["type"] == "function_call" and fc["call_id"] == "c1" and fc["name"] == "bash"
    assert json.loads(fc["arguments"]) == {"cmd": "ls"}
    assert items[2] == {"type": "function_call_output", "call_id": "c1", "output": "a.py"}


def test_translate_input_user_image():
    a = CodexAdapter()
    instr, items = a._translate_input([Message(role="user", content="see this",
                                               images=[ImagePart("image/png", "AAAA")])])
    content = items[0]["content"]
    img = [c for c in content if c["type"] == "input_image"][0]
    assert img["image_url"] == "data:image/png;base64,AAAA"


def test_parse_stream_text_tool_usage():
    a = CodexAdapter()
    chunks = [
        {"type": "response.created", "response": {"id": "r"}},
        {"type": "response.output_text.delta", "delta": "Hello "},
        {"type": "response.output_text.delta", "delta": "world"},
        {"type": "response.output_item.done",
         "item": {"type": "function_call", "call_id": "c1", "name": "bash",
                  "arguments": "{\"cmd\": \"ls\"}"}},
        {"type": "response.completed",
         "response": {"status": "completed",
                      "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}}},
    ]
    events = list(a._parse_stream(iter(chunks)))
    texts = [e.text for e in events if isinstance(e, TextDelta)]
    assert "".join(texts) == "Hello world"
    tcs = [e for e in events if isinstance(e, ToolCall)]
    assert tcs and tcs[0].name == "bash" and tcs[0].arguments == {"cmd": "ls"}
    usages = [e for e in events if isinstance(e, Usage)]
    assert usages and usages[-1].total == 13
    assert any(isinstance(e, Done) for e in events)


def test_parse_stream_failed_raises():
    import pytest
    a = CodexAdapter()
    chunks = [{"type": "response.failed", "response": {"error": {"message": "boom"}}}]
    with pytest.raises(RuntimeError):
        list(a._parse_stream(iter(chunks)))


def test_codex_available_reads_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    # no auth.json yet
    assert codex_creds.codex_available() is False
    (tmp_path / "auth.json").write_text(json.dumps(
        {"auth_mode": "chatgpt", "tokens": {"access_token": "tok", "account_id": "acct"}}))
    assert codex_creds.codex_available() is True
    tok, acct = codex_creds.codex_auth()
    assert tok == "tok" and acct == "acct"

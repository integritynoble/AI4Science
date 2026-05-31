from pathlib import Path
from ai4science.harness.session import AgentSession
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, Done


def test_common_session_streams_text(tmp_path, capsys):
    sess = AgentSession(
        adapter=StubAdapter([[TextDelta("hello "), TextDelta("world"), Done("end")]]),
        model="stub", backend="anthropic", workspace=tmp_path,
        read_only=True, auto_yes=False,
        on_text=lambda t: print(t, end=""), meter=lambda u: None,
    )
    out = sess.run_turn("say hi")
    assert out == "hello world"
    assert "hello world" in capsys.readouterr().out

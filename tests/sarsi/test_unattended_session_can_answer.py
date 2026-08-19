"""An unattended session has nobody to answer an approval prompt.

`ai4science chat` gates every Edit/Write/Bash behind a prompt. A supervised
session is driven by a loop that types instructions, not by a person watching —
so every gated tool call stopped at a question no one was there to answer, and
the session sat there looking busy. `sarsi-claude` never had this problem,
because `claude` is launched with its own governance and no prompt.

So a GOVERNED session auto-approves, and the ceiling does the constraining:
`ensure_governance_hook` is wired before launch and carries the same declared
paths, so the boundary is the hook rather than a prompt that cannot be reached.
An UNGOVERNED session keeps the prompt, because there it is the only control
there is — auto-approving one of those would remove the last thing in the way.

A note on how this is tested, because the first attempt at proving it was
worthless. `MachineRuntime.start` imports `sessions` INSIDE the function body,
so patching the attribute on the `session` module intercepts nothing and the
recorder stays empty. An empty recorder then reads exactly like a passing
assertion. Patch the real target — `machine.sessions.start_session` — or prove
nothing while appearing to prove something.
"""
import pytest

from ai4science.harness.agents.machine import sessions as machine_sessions
from ai4science.harness.agents.sarsi.session import MachineRuntime


@pytest.fixture
def launched(monkeypatch):
    """Every `start_session` call, as the launcher really received it."""
    calls = []

    def _fake(name, cwd, **kw):
        calls.append(kw)
        return {"ok": True, "name": name}

    monkeypatch.setattr(machine_sessions, "start_session", _fake)
    return calls


def test_a_governed_session_can_answer_its_own_prompts(launched, tmp_path):
    MachineRuntime().start("t", str(tmp_path), govern=True, ceiling="A2",
                           spec="ai4sci", writable=[str(tmp_path)])
    assert "--yes" in launched[0]["claude_bin"]


def test_an_ungoverned_session_keeps_the_prompt(launched, tmp_path):
    """The prompt is the only control an ungoverned session has."""
    MachineRuntime().start("t", str(tmp_path), govern=False, ceiling="A2",
                           spec="ai4sci", writable=[str(tmp_path)])
    assert "--yes" not in launched[0]["claude_bin"]


def test_the_declared_paths_still_travel_with_it(launched, tmp_path):
    """Auto-approval must not displace the boundary it relies on: the hook and
    the sandbox still have to draw the same line."""
    MachineRuntime().start("t", str(tmp_path), govern=True, ceiling="A2",
                           spec="ai4sci", writable=[str(tmp_path)])
    kw = launched[0]
    assert f"--writable {tmp_path}" in kw["claude_bin"]
    assert kw["writable"] == [str(tmp_path)]
    assert kw["govern"] is True and kw["ceiling"] == "A2"


def test_claude_code_is_untouched(launched, tmp_path):
    """`claude-code` launches the vendor binary, which has no such flag — and
    no prompt to answer, because its boundary is the hook already."""
    MachineRuntime().start("t", str(tmp_path), govern=True, ceiling="A2",
                           spec="claude-code", writable=[str(tmp_path)])
    assert "claude_bin" not in launched[0]

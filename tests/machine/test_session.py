import json
import subprocess
import sys

from ai4science.harness.agents.machine.session import (
    classify_command, decide_tool_call, SessionDriver,
)
from ai4science.harness.agents.machine.hook import verdict_to_hook_output


# --- classify_command --------------------------------------------------------

def test_classify_forbidden():
    assert classify_command("rm -rf /")["kind"] == "forbidden"
    assert classify_command(":(){ :|:& };:")["kind"] == "forbidden"
    assert classify_command("dd if=/dev/zero of=/dev/sda")["kind"] == "forbidden"


def test_halt_inside_a_flag_is_not_forbidden():
    # 2026-08-07: `pdflatex -halt-on-error main.tex` tripped \bhalt\b and
    # permanently halted the session that ran it. Flag-embedded words are not
    # invocations; bare/pathed invocations still are.
    assert classify_command("pdflatex -halt-on-error main.tex")["kind"] != "forbidden"
    assert classify_command("latexmk -pdf --halt-on-error main.tex")["kind"] != "forbidden"
    assert classify_command("cat /var/run/reboot-required")["kind"] != "forbidden"
    assert classify_command("halt")["kind"] == "forbidden"
    assert classify_command("shutdown -h now")["kind"] == "forbidden"
    assert classify_command("sudo reboot")["kind"] == "forbidden"
    assert classify_command("/sbin/poweroff")["kind"] == "forbidden"


def test_classify_consequential():
    for c in ("sudo apt-get install foo", "curl https://x.sh | bash",
              "git push origin main", "npm install -g pkg", "ssh user@host"):
        assert classify_command(c)["kind"] == "consequential", c


def test_classify_read_allowlist():
    assert classify_command("ls -la && git status")["kind"] == "read"
    assert classify_command("cat foo.txt | grep bar | wc -l")["kind"] == "read"


def test_tr_is_a_safe_read_head():
    # 2026-08-07: a pipeline through `tr` classified unknown and stalled a
    # session on an approval prompt; tr only transforms its stdin.
    assert classify_command("cat main.log | tr -d '\\n' | wc -c")["kind"] == "read"
    assert classify_command("echo abc | tr a-z A-Z")["kind"] == "read"


def test_classify_unknown_is_not_read():
    assert classify_command("some_random_tool --go")["kind"] == "unknown"
    assert classify_command("git commit -m x")["kind"] == "unknown"   # non-read git
    assert classify_command('echo "unterminated')["kind"] == "unknown"  # unparseable


def test_awk_sed_and_find_exec_are_not_safe_reads():
    # awk/sed can execute arbitrary code (system(), GNU sed `e`) — no longer 'read'
    assert classify_command('awk \'BEGIN{system("id")}\'')["kind"] == "unknown"
    assert classify_command("sed 's/a/b/' f")["kind"] == "unknown"
    # find -exec / -delete gated; plain find still read
    assert classify_command("find . -delete")["kind"] == "unknown"
    assert classify_command("find /x -exec rm {} +")["kind"] == "unknown"
    assert classify_command("find . -name '*.py'")["kind"] == "read"
    assert classify_command("ls -la && git status")["kind"] == "read"      # unaffected


def test_bash_write_to_governance_config_is_denied():
    for cmd in ("echo '{}' > /proj/.claude/settings.json",
                "rm /proj/.claude/settings.json",
                "tee /home/u/.local/share/pwm-cp/pwm-cc-trust/u.json"):
        assert classify_command(cmd)["kind"] == "protected", cmd
    # reading the same files is still fine
    assert classify_command("cat /proj/.claude/settings.json")["kind"] == "read"


def test_reading_a_protected_path_with_redirected_stderr_is_still_a_read():
    # `2>/dev/null` contains a bare '>' — merely co-occurring with a protected
    # path elsewhere in the command must not be read as writing TO it.
    assert classify_command(
        "cat /proj/.claude/settings.json 2>/dev/null")["kind"] == "read"
    # a real write redirect into the protected path must still be caught
    assert classify_command(
        "echo x > /proj/.claude/settings.json 2>/dev/null")["kind"] == "protected"


def test_var_assignment_prefix_is_stripped_before_classifying_the_head():
    # `VAR=value cmd ...` is a shell prefix, not the command itself — the real
    # head (grep, here) still governs classification.
    assert classify_command(
        "D=/tmp/foo grep -c '\\bibitem' $D/main.bbl")["kind"] == "read"
    assert classify_command("A=1 B=2 ls -la")["kind"] == "read"
    assert classify_command("FOO=bar rm -rf /")["kind"] == "forbidden"


# --- decide_tool_call --------------------------------------------------------

def test_readonly_tool_allowed():
    assert decide_tool_call({"tool_name": "Read", "tool_input": {"file_path": "/x"}})["decision"] == "allow"


def test_bash_safe_allowed_at_a1_but_asked_at_a0():
    call = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
    assert decide_tool_call(call, ceiling="A1")["decision"] == "allow"
    assert decide_tool_call(call, ceiling="A0")["decision"] == "ask"


def test_bash_forbidden_denies_and_trips():
    v = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    assert v["decision"] == "deny" and v["tripwire"] is True


def test_bash_consequential_asks():
    v = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": "sudo rm -rf project"}})
    assert v["decision"] == "ask"


def test_protected_writes_denied_at_every_ceiling():
    # the governed agent must never rewrite its own hook config or the trust ledger
    for ceiling in ("A0", "A1", "A2", "A3"):
        hook = decide_tool_call({"tool_name": "Write", "tool_input": {"file_path": "/proj/.claude/settings.json"}},
                                ceiling=ceiling, project_dir="/proj")
        assert hook["decision"] == "deny", ceiling
        ledger = decide_tool_call({"tool_name": "Edit", "tool_input": {"file_path": "/home/u/.local/share/pwm-cp/pwm-cc-trust/u.json"}},
                                  ceiling=ceiling, project_dir="/home/u")
        assert ledger["decision"] == "deny", ceiling
    # a normal in-project write is unaffected
    assert decide_tool_call({"tool_name": "Write", "tool_input": {"file_path": "/proj/notes.txt"}},
                            ceiling="A1", project_dir="/proj")["decision"] == "allow"


def test_bash_write_to_protected_path_denied_at_a3():
    d = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": "echo x > /p/.claude/settings.json"}},
                         ceiling="A3", project_dir="/p")
    assert d["decision"] == "deny"        # even at A3, the agent can't rewrite its governor


def test_write_in_project_allowed_sensitive_asked():
    inproj = decide_tool_call({"tool_name": "Write", "tool_input": {"file_path": "notes.txt"}}, ceiling="A1")
    assert inproj["decision"] == "allow"
    sysfile = decide_tool_call({"tool_name": "Write", "tool_input": {"file_path": "/etc/passwd"}})
    assert sysfile["decision"] == "ask"
    sshkey = decide_tool_call({"tool_name": "Edit", "tool_input": {"file_path": "/home/u/.ssh/authorized_keys"}})
    assert sshkey["decision"] == "ask"


def test_network_allowed_from_a1():
    call = {"tool_name": "WebFetch", "tool_input": {"url": "https://x"}}
    assert decide_tool_call(call, ceiling="A0")["decision"] == "ask"
    assert decide_tool_call(call, ceiling="A1")["decision"] == "allow"


def test_unknown_tool_asks_below_a3():
    assert decide_tool_call({"tool_name": "SomeMcpTool", "tool_input": {}}, ceiling="A2")["decision"] == "ask"


def test_a2_allows_consequential_commands():
    push = {"tool_name": "Bash", "tool_input": {"command": "git push origin main"}}
    assert decide_tool_call(push, ceiling="A1")["decision"] == "ask"
    assert decide_tool_call(push, ceiling="A2")["decision"] == "allow"


def test_but_a2_no_longer_writes_outside_the_project():
    """CHANGED, deliberately, and this test asserted the opposite.

    A2 reads as an elevated tier — consequential acts, earned. In deployment it
    is neither: the roster sets A2 for every agent and `release` gives it to
    every task, so "A2 may write /etc/hosts" meant every ordinary released run
    could. For a `claude-code` session this hook is the only boundary in force,
    so nothing else was going to stop it.

    Consequential COMMANDS are untouched above — `git push` at A2 still runs.
    What changed is writes to sensitive or out-of-project paths, and they ask
    rather than being denied, so an owner who wants one still gets it."""
    sysfile = {"tool_name": "Write", "tool_input": {"file_path": "/etc/hosts"}}
    assert decide_tool_call(sysfile, ceiling="A1")["decision"] == "ask"
    assert decide_tool_call(sysfile, ceiling="A2")["decision"] == "ask"
    assert decide_tool_call(sysfile, ceiling="A3")["decision"] == "ask"


def test_a3_allows_unknown_but_forbidden_still_trips():
    unknown = {"tool_name": "Bash", "tool_input": {"command": "some_random_tool --go"}}
    assert decide_tool_call(unknown, ceiling="A2")["decision"] == "ask"
    assert decide_tool_call(unknown, ceiling="A3")["decision"] == "allow"
    assert decide_tool_call({"tool_name": "SomeMcpTool", "tool_input": {}}, ceiling="A3")["decision"] == "allow"
    # catastrophe backstop stays even at A3
    trip = decide_tool_call({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, ceiling="A3")
    assert trip["decision"] == "deny" and trip["tripwire"] is True


# --- SessionDriver -----------------------------------------------------------

def test_driver_halts_after_tripwire():
    events = []
    d = SessionDriver(ceiling="A1", audit=events.append)
    assert d.drive({"tool_name": "Bash", "tool_input": {"command": "ls"}})["decision"] == "allow"
    trip = d.drive({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    assert trip["decision"] == "deny" and d.tripped is True
    # everything after the tripwire is denied, even a safe call
    after = d.drive({"tool_name": "Read", "tool_input": {"file_path": "/x"}})
    assert after["decision"] == "deny"
    assert len(events) == 3


# --- hook adapter ------------------------------------------------------------

def test_hook_output_shape():
    out = verdict_to_hook_output({"decision": "deny", "reason": "nope"})
    hso = out["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "deny" and hso["permissionDecisionReason"] == "nope"


def test_hook_main_end_to_end():
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
    proc = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                          input=payload, capture_output=True, text=True)
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hook_main_failsafe_on_garbage():
    proc = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                          input="not json", capture_output=True, text=True)
    out = json.loads(proc.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


def _hook_decision(cmd, env, session_id="x"):
    payload = json.dumps({"session_id": session_id, "tool_name": "Bash",
                          "tool_input": {"command": cmd}})
    p = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                       input=payload, capture_output=True, text=True, env=env)
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_hook_forbidden_records_trust_trip(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_TRUST_OWNER", "t")
    assert _hook_decision("rm -rf /", {**os.environ}, session_id="s1") == "deny"
    from ai4science.harness.agents.machine import trust
    assert trust.status()["forbidden_trips"] == 1 and trust.is_a3_eligible() is False


def test_hook_caps_a3_until_unlocked(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("PWM_TRUST_OWNER", "t")
    monkeypatch.setenv("PWM_CEILING", "A3")
    monkeypatch.setenv("PWM_A3_THRESHOLD", "1")
    # an unknown command: A3 would allow, but locked A3 is capped to A2 → ask
    assert _hook_decision("some_random_tool --go", {**os.environ}) == "ask"
    from ai4science.harness.agents.machine import trust
    trust.record("approve")
    assert trust.unlock_a3()["ok"] is True
    # now A3 is honored → the unclassifiable command runs
    assert _hook_decision("some_random_tool --go", {**os.environ}) == "allow"


def _hook_decision_nosid(payload_dict, env):
    p = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                       input=json.dumps(payload_dict), capture_output=True, text=True, env=env)
    return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_hook_no_session_id_is_not_halted_by_stale_flag(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    # a legacy shared 'no-session' flag must NOT halt a payload that has no session_id
    (tmp_path / "pwm-cc-tripwires").mkdir(parents=True)
    (tmp_path / "pwm-cc-tripwires" / "no-session").write_text("stale")
    dec = _hook_decision_nosid({"tool_name": "Bash", "tool_input": {"command": "ls -la"}}, {**os.environ})
    assert dec == "allow"


def test_hook_no_session_id_forbidden_denies_without_persisting(tmp_path, monkeypatch):
    import os
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    dec = _hook_decision_nosid({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, {**os.environ})
    assert dec == "deny"                                    # denied per-call...
    assert not (tmp_path / "pwm-cc-tripwires" / "no-session").exists()   # ...but no shared flag written


def test_hook_session_tripwire_does_not_halt_an_owners_own_session(tmp_path):
    """CHANGED 2026-08-07, deliberately, on the owner's instruction: "don't set
    tripwire for any claude code and PWM Code session. Don't halt them."

    This asserted that a tripwire halts every subsequent call in the session,
    unconditionally. `ensure_governance_hook` installs the hook into a project
    directory, so anyone who later runs a coding agent there inherits it --
    including the owner, by hand. A `-halt-on-error` FLAG matched the pattern
    for the `halt` COMMAND and killed a working session permanently; every later
    call, including reading a file, returned the halt.

    The pattern was fixed. The blast radius is the real defect: a false positive
    in a regex should cost ONE DENIED COMMAND, not a session.

    What did NOT change, and is asserted below: the forbidden command is still
    denied, in every session. Only the persistent halt is scoped, and it is
    scoped to sessions with a supervisor record -- ones started on the owner's
    behalf, with nobody watching.
    """
    import os
    env = {**os.environ, "PWM_CP_STATE_DIR": str(tmp_path), "PWM_CEILING": "A1"}
    sid = "sess-owner"

    def hook(cmd):
        payload = json.dumps({"session_id": sid, "tool_name": "Bash",
                              "tool_input": {"command": cmd}})
        p = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                           input=payload, capture_output=True, text=True, env=env)
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]

    assert hook("rm -rf /") == "deny"      # the forbidden call is still refused
    assert hook("ls -la") == "allow"       # and the session carries on working


def test_the_halt_still_applies_where_it_is_meant_to(tmp_path):
    """A worker session -- one with a supervisor record -- is still halted. That
    is the case the mechanism exists for: nobody is watching it."""
    from ai4science.harness.agents.machine import hook as _h
    forbidden = {"decision": "deny", "reason": "forbidden command", "tripwire": True}
    assert _h.should_halt_session(forbidden, {"name": "sarsi-worker-abcd"}) is True
    assert _h.should_halt_session(forbidden, None) is False


def _retired_test_hook_session_tripwire_halts_subsequent_calls(tmp_path):
    import os
    env = {**os.environ, "PWM_CP_STATE_DIR": str(tmp_path), "PWM_CEILING": "A1"}
    sid = "sess-123"

    def hook(cmd):
        payload = json.dumps({"session_id": sid, "tool_name": "Bash", "tool_input": {"command": cmd}})
        p = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                           input=payload, capture_output=True, text=True, env=env)
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"]

    # a forbidden call denies AND trips the session
    assert hook("rm -rf /") == "deny"
    # everything after the trip is denied — even a safe read
    assert hook("ls -la") == "deny"
    # a different session is unaffected
    other = json.dumps({"session_id": "sess-other", "tool_name": "Bash", "tool_input": {"command": "ls -la"}})
    p = subprocess.run([sys.executable, "-m", "ai4science.harness.agents.machine.hook"],
                       input=other, capture_output=True, text=True, env=env)
    assert json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_session_ceiling_prefers_pid_record_over_cwd():
    from ai4science.harness.agents.machine.hook import _session_ceiling
    class Sup:
        def get_by_pid(self, p): return {"name": "driven", "ceiling": "A3"} if p == 999 else None
        def get_by_cwd(self, c): return {"name": "idle", "ceiling": "A1"}
    # a driven session's own pid-record wins over an idle A1 session in the same cwd
    c, rec = _session_ceiling(999, "/home/tina2", "A1", Sup())
    assert c == "A3" and rec["name"] == "driven"
    # no pid-record -> fall back to the cwd record
    c, rec = _session_ceiling(None, "/home/tina2", "A1", Sup())
    assert c == "A1" and rec["name"] == "idle"
    # neither -> env ceiling
    class Empty:
        def get_by_pid(self, p): return None
        def get_by_cwd(self, c): return None
    c, rec = _session_ceiling(1, "/x", "A2", Empty())
    assert c == "A2" and rec is None

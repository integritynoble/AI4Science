from ai4science.harness.agents.machine.agent import run_machine
from ai4science.harness.agents.machine.operations import default_operations, Operation

LINUX = {"os": "linux", "arch": "x86_64", "installed": {"claude": False}, "supported": True}
MAC = {"os": "macos", "arch": "arm64", "installed": {"claude": True}, "supported": True}


def _approve_all(op, ctx):
    return True


def _deny_all(op, ctx):
    return False


def test_refuses_intent_with_no_vetted_operation():
    # no arbitrary-command path: an unknown intent is refused, not attempted
    out = run_machine(intent="rm -rf / please", caps=LINUX, approve=_approve_all)
    assert out["status"] == "refused"
    assert "no arbitrary commands" in out["reason"] or "vetted" in out["reason"]


def test_readonly_detect_runs_without_approval():
    out = run_machine(intent="what os am i on / capabilities", caps=LINUX)
    assert out["status"] == "done" and out["op"] == "detect"
    assert out["result"]["os"] == "linux"


def test_required_permissions_are_specific_not_blanket():
    out = run_machine(intent="what permissions does claude need", caps=LINUX)
    assert out["status"] == "done" and out["op"] == "required_permissions"
    perms = out["result"]["claude_permissions"]
    assert "fs:project-dir" in perms and "net:anthropic-api" in perms
    assert "*" not in perms and "all" not in perms       # least privilege, no blanket grant


def test_install_needs_approval_and_never_runs_without_it():
    ran = []
    def spy_execute(op, caps):
        ran.append(op.name)
        return {"ran": True}
    out = run_machine(intent="install claude code", caps=LINUX, approve=_deny_all, execute=spy_execute)
    assert out["status"] == "needs_approval" and out["op"] == "install_claude_code"
    assert "claude.ai/install.sh" in " ".join(out["recipe"])
    assert ran == []                                     # the recipe never executed


def test_install_executes_the_vetted_recipe_after_approval_and_audits():
    events = []
    def spy_execute(op, caps):
        return {"ran": True, "argv": list(op.recipe_for(caps["os"])), "ok": True}
    out = run_machine(intent="install claude code", caps=LINUX,
                      approve=_approve_all, execute=spy_execute, audit=events.append)
    assert out["status"] == "done" and out["op"] == "install_claude_code"
    assert out["result"]["ran"] is True and out["result"]["ok"] is True
    assert any(e.get("op") == "install_claude_code" and e.get("outcome") == "executed" for e in events)


def test_login_uses_broker_and_never_sees_the_secret():
    class Broker:
        def lease(self, scope):
            return {"lease_id": "L1", "scope": scope}   # a handle, NOT the token
    out = run_machine(intent="log in to my claude account", caps=LINUX,
                      approve=_approve_all, broker=Broker())
    assert out["status"] == "done" and out["op"] == "broker_login"
    assert out["result"]["leased"] is True and out["result"]["lease_id"] == "L1"
    # the result carries no secret material
    assert "token" not in out["result"] and "secret" not in out["result"]


def test_login_blocked_without_a_broker():
    out = run_machine(intent="login to my account", caps=LINUX, approve=_approve_all, broker=None)
    assert out["status"] == "blocked" and "broker" in out["reason"]


def test_os_unsupported_operation_is_not_executed():
    # an op restricted to some OSes is refused on others (here: force a linux-only op on macOS)
    linux_only = (Operation("linux_thing", "linux only", ("linux",), "install",
                            match=("do the thing",), recipes={"linux": ("true",)}),)
    ran = []
    out = run_machine(intent="do the thing", caps=MAC, registry=linux_only,
                      approve=_approve_all, execute=lambda o, c: ran.append(1))
    assert out["status"] == "unsupported" and out["op"] == "linux_thing"
    assert ran == []


def test_registry_has_no_arbitrary_command_operation():
    # structural guarantee: nothing in the registry runs a caller-supplied command
    for op in default_operations():
        assert op.side_effect in {"read", "install", "config", "credential"}
        # recipes are fixed argv tuples, never templated with free input
        for argv in op.recipes.values():
            assert isinstance(argv, tuple)

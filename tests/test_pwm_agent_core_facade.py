import pwm_agent_core as core

def test_contract_surface_present():
    for name in ("AgentSpec", "BuildContext", "Tool", "reload", "get",
                 "dispatchable_targets", "build_registry_for",
                 "register_agent_bundle", "run_cli"):
        assert hasattr(core, name), f"missing {name}"

def test_versions_exposed():
    assert isinstance(core.CONTRACT_VERSION, int) and core.CONTRACT_VERSION >= 1
    assert isinstance(core.__version__, str) and core.__version__

def test_agentspec_is_the_real_type():
    from ai4science.harness.agents.spec import AgentSpec as Real
    assert core.AgentSpec is Real

def test_run_cli_sets_mode_not_agent(monkeypatch):
    import os
    import ai4science.cli as cli
    from ai4science.harness.agents import registry
    called = {}
    monkeypatch.setattr(cli, "main", lambda: called.setdefault("ran", True))
    monkeypatch.setattr(registry, "reload", lambda *a, **k: None)  # keep test hermetic
    monkeypatch.delenv("AI4SCIENCE_AGENT", raising=False)
    saved = os.environ.get("AI4SCIENCE_MODE")
    os.environ.pop("AI4SCIENCE_MODE", None)
    try:
        import pwm_agent_core as core
        core.run_cli(default_agent="research")
        assert os.environ.get("AI4SCIENCE_MODE") == "research"
        assert os.environ.get("AI4SCIENCE_AGENT") is None   # engine selector left untouched
        assert called.get("ran") is True
    finally:
        if saved is None:
            os.environ.pop("AI4SCIENCE_MODE", None)
        else:
            os.environ["AI4SCIENCE_MODE"] = saved

def test_run_cli_reloads_registry_before_launching(monkeypatch):
    import pwm_agent_core as core
    from ai4science.harness.agents import registry
    import ai4science.cli as cli
    calls = []
    monkeypatch.setattr(registry, "reload", lambda *a, **k: calls.append("reload"))
    monkeypatch.setattr(cli, "main", lambda: calls.append("main"))
    core.run_cli(default_agent="research")
    assert calls == ["reload", "main"], calls

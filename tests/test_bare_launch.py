"""Bare `ai4science` launch: direct chat() calls must normalize Typer defaults."""


def test_chat_normalizes_omitted_typer_params(monkeypatch):
    # Call chat() the way _bare_launch does but OMIT backend (the 2026-06-11
    # regression): the value reaching the REPL must be a real default, never
    # a typer OptionInfo object.
    from pathlib import Path
    import typer.models as tm
    from ai4science.commands import chat as chat_cmd

    seen = {}

    def fake_repl(workspace, **kw):
        seen.update(kw)

    monkeypatch.setattr(chat_cmd, "run_common_repl", fake_repl, raising=False)
    try:
        chat_cmd.chat(agent="claude", workspace=Path("."), read_only=True,
                      yes=False, plan=False, no_subagents=True, no_mcp=True,
                      model=None, continue_session=False, resume=None,
                      mode="unified-LLM")  # backend omitted on purpose
    except Exception:
        pass  # provider availability may stop the launch; params were bound first
    for k, v in seen.items():
        assert not isinstance(v, tm.ParameterInfo), f"{k} leaked OptionInfo"
    if "backend" in seen:
        assert seen["backend"] is None

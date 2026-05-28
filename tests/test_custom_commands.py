"""Tests for custom (user-defined) slash commands."""
from __future__ import annotations

from pathlib import Path

from ai4science.commands.custom_commands import (
    load_custom_commands, expand_command, command_dirs,
)


def _mk_cmd(workspace: Path, name: str, body: str) -> Path:
    d = workspace / ".ai4science" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.md"
    f.write_text(body, encoding="utf-8")
    return f


def test_no_commands(tmp_path):
    assert load_custom_commands(tmp_path) == {}


def test_load_project_command(tmp_path):
    _mk_cmd(tmp_path, "tighten", "Tighten tolerance_epsilon in spec.md to $ARGUMENTS.")
    cmds = load_custom_commands(tmp_path)
    assert "tighten" in cmds
    assert cmds["tighten"].name == "tighten.md"


def test_command_name_is_lowercased(tmp_path):
    _mk_cmd(tmp_path, "Review", "review it")
    cmds = load_custom_commands(tmp_path)
    assert "review" in cmds


def test_expand_arguments_substitution(tmp_path):
    f = _mk_cmd(tmp_path, "tighten",
                "Set tolerance_epsilon to $ARGUMENTS in spec.md and re-validate.")
    out = expand_command(f, "0.003")
    assert out == "Set tolerance_epsilon to 0.003 in spec.md and re-validate."


def test_expand_positional_substitution(tmp_path):
    f = _mk_cmd(tmp_path, "swap", "Change $1 to $2 in the spec.")
    out = expand_command(f, "tolerance_epsilon 0.005")
    assert out == "Change tolerance_epsilon to 0.005 in the spec."


def test_expand_missing_positionals_become_empty(tmp_path):
    f = _mk_cmd(tmp_path, "x", "value=$1 extra=$2")
    out = expand_command(f, "only-one")
    assert out == "value=only-one extra="


def test_project_overrides_user(tmp_path, monkeypatch):
    # User-level command
    user_cfg = tmp_path / "userconfig"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_cfg))
    (user_cfg / "ai4science" / "commands").mkdir(parents=True)
    (user_cfg / "ai4science" / "commands" / "go.md").write_text("USER version")
    # Project-level command with same name
    ws = tmp_path / "ws"
    _mk_cmd(ws, "go", "PROJECT version")

    cmds = load_custom_commands(ws)
    assert cmds["go"].read_text() == "PROJECT version"   # project wins


def test_command_dirs_includes_project_and_user(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    dirs = command_dirs(tmp_path / "ws")
    assert dirs[0] == (tmp_path / "ws").resolve() / ".ai4science" / "commands"
    assert dirs[1] == tmp_path / "cfg" / "ai4science" / "commands"

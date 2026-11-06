"""Keep the documented ai4science command paths and flags in sync with the CLI."""
from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest
from typer.main import get_command

from ai4science.cli import app

REPO = Path(__file__).resolve().parents[2]
DOCS = (
    "docs/INSTALL.md",
    "docs/AI4SCIENCE_USAGE.md",
    "docs/AI4SCIENCE_USER_MANUAL.md",
    "docs/REPL_SARSI_WORKER_GUIDE.md",
    "docs/USING_SARSI_WORKER.md",
)
CLI = Path(sys.executable).with_name("ai4science")

# Keep an entry here only when a documented path cannot be repaired. The reason
# is shown in failures so a future update can remove the exception deliberately.
KNOWN_BAD_COMMANDS: dict[tuple[str, ...], str] = {}


def _examples():
    for doc in DOCS:
        path = REPO / doc
        fenced = False
        for line_number, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if not fenced or not line.strip().startswith("ai4science"):
                continue
            try:
                words = shlex.split(line.strip(), comments=True)
            except ValueError:
                words = line.strip().split()
            if words and words[0] == "ai4science":
                yield doc, line_number, line.strip(), words[1:]


def _longest_path(words):
    """Resolve subcommands from Typer's command tree without running a command."""
    command = get_command(app)
    path = []
    for word in words:
        if word.startswith("-") or word.startswith("<"):
            break
        children = getattr(command, "commands", {})
        if word in children:
            path.append(word)
            command = children[word]
        elif path:
            # A nested group accepts only registered subcommands at this point.
            if children:
                return tuple(path), word
            break
        else:
            # The root also accepts a free-form prompt as its input.
            break
    return tuple(path), None


def _help(path):
    return subprocess.run(
        [str(CLI), *path, "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("path", sorted({
    _longest_path(words)[0] for _, _, _, words in _examples()
}))
def test_documented_subcommand_path_exits_successfully_on_help(path):
    result = _help(path)
    if path in KNOWN_BAD_COMMANDS:
        pytest.xfail(KNOWN_BAD_COMMANDS[path])
    assert result.returncode == 0, (
        f"ai4science {' '.join(path)} --help exited {result.returncode}:\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_documented_commands_use_registered_subcommands_and_flags():
    for doc, line_number, command, words in _examples():
        path, unknown = _longest_path(words)
        if unknown is not None:
            assert path in KNOWN_BAD_COMMANDS, (
                f"{doc}:{line_number}: unknown subcommand {unknown!r} in {command}"
            )
            continue
        result = _help(path)
        if path in KNOWN_BAD_COMMANDS:
            continue
        help_text = result.stdout + result.stderr
        flags = {
            word for word in words
            if re.fullmatch(r"--[A-Za-z][A-Za-z0-9-]*", word)
        }
        missing = sorted(
            flag for flag in flags
            if re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", help_text) is None
        )
        assert result.returncode == 0, (
            f"{doc}:{line_number}: help failed for {command}:\n{help_text}"
        )
        assert not missing, (
            f"{doc}:{line_number}: flags absent from ai4science {' '.join(path)} "
            f"--help: {', '.join(missing)} ({command})"
        )

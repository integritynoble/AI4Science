"""Telling the session which directories its writing tools may write.

dev54 made the plan's declared working directory writable by `write` and `edit`.
The very next live run showed that was half the job: `abraham`, left alone,
still reached for

    cat << 'EOF' > /home/grace/live-abraham/weekly-review.md

It was no longer *forced* into a heredoc — it simply had no reason to believe
the tool would work. The sandbox had said "path escapes the workspace" for the
whole life of the tool description that says "Write (overwrite) a file"; from
inside the session, a shell redirect is the thing that has always worked. It
took an owner refusing the gate and saying so for it to use `write`, and the
report showed the split exactly: **2 writes observed, 5 shell commands
unchecked**.

Capability without discoverability changes nothing on its own. So the roots go
where the model actually looks — the tool's own description:

  * **named, not merely implied.** "Paths outside the workspace are refused"
    would leave the agent guessing which ones; the directories are listed.
  * **on the tools it constrains.** `write` and `edit` are sandboxed; `read`,
    `glob` and `grep` never were, and adding a boundary note to them would
    describe a restriction that does not exist.
  * **`bash` says the quiet part.** Its `cmd` is not path-checked, so a heredoc
    reaches anywhere the process can — which is exactly why choosing it costs
    the reader their record of what happened. It points at `write` for writing
    a named file.
  * **nothing declared says nothing.** Most sessions have no extra roots, and
    inventing a sentence about a boundary that has not moved is noise that the
    model has to reconcile against what it observes.
"""
from pathlib import Path

import pytest

from ai4science.harness.tools import default_registry


def _desc(reg, name):
    return {s.name: s.description for s in reg.specs()}[name]


@pytest.fixture
def declared(tmp_path):
    d = tmp_path / "live-abraham"
    d.mkdir()
    return d


# ── the roots are named where the model looks ─────────────────────────

def test_write_names_the_declared_directory(declared):
    reg = default_registry(writable_roots=[declared])
    assert str(declared) in _desc(reg, "write")


def test_edit_names_it_too(declared):
    """It is sandboxed by the same rule, so it carries the same fact."""
    reg = default_registry(writable_roots=[declared])
    assert str(declared) in _desc(reg, "edit")


def test_several_roots_are_all_named(tmp_path):
    a, b = tmp_path / "one", tmp_path / "two"
    a.mkdir(); b.mkdir()
    said = _desc(default_registry(writable_roots=[a, b]), "write")
    assert str(a) in said and str(b) in said


def test_it_says_they_are_writable_rather_than_merely_listing_them(declared):
    said = _desc(default_registry(writable_roots=[declared]), "write").lower()
    assert "write" in said and ("also" in said or "outside" in said)


# ── and nowhere else ──────────────────────────────────────────────────

def test_read_is_unchanged(declared):
    """`read` was never sandboxed. A boundary note there would describe a
    restriction that does not exist."""
    plain = _desc(default_registry(), "read")
    assert _desc(default_registry(writable_roots=[declared]), "read") == plain


def test_glob_and_grep_are_unchanged(declared):
    with_roots = default_registry(writable_roots=[declared])
    plain = default_registry()
    for name in ("glob", "grep"):
        assert _desc(with_roots, name) == _desc(plain, name)


def test_with_nothing_declared_the_descriptions_do_not_move(declared):
    """Most sessions declare no extra root. A sentence about a boundary that
    has not moved is noise the model must reconcile against what it sees."""
    plain = default_registry()
    same = default_registry(writable_roots=[])
    for name in ("write", "edit", "bash", "read"):
        assert _desc(same, name) == _desc(plain, name)


# ── bash is pointed away from, honestly ───────────────────────────────

def test_bash_says_writing_a_named_file_belongs_in_write(declared):
    """Not "bash is forbidden" — it is not. The reason is what the reader
    loses: a heredoc names no file, so nothing afterwards can say what it
    touched."""
    said = _desc(default_registry(writable_roots=[declared]), "bash").lower()
    assert "write" in said


def test_bash_does_not_claim_to_be_sandboxed(declared):
    """Its `cmd` is not path-checked and never was. Saying otherwise in the
    description would be a false assurance in the one place a reader would
    take it literally."""
    said = _desc(default_registry(writable_roots=[declared]), "bash").lower()
    assert "sandboxed to" not in said
    assert "cannot write outside" not in said


# ── it reaches the running session ────────────────────────────────────

def test_the_session_builds_its_tools_with_the_roots_it_was_given(declared,
                                                                   tmp_path):
    """The end of the chain: `AgentSession` already takes `writable_roots` for
    the GATE. The description is built from the same value, so what the agent
    is told and what it is allowed cannot drift apart."""
    from ai4science.harness.session import AgentSession

    s = AgentSession(adapter=None, model="m", backend="b",
                     workspace=tmp_path, writable_roots=[declared])
    assert str(declared) in _desc(s.registry, "write")


def test_a_session_with_no_roots_says_nothing_extra(tmp_path):
    from ai4science.harness.session import AgentSession

    s = AgentSession(adapter=None, model="m", backend="b", workspace=tmp_path)
    assert _desc(s.registry, "write") == _desc(default_registry(), "write")


# ── the path a real session actually takes ────────────────────────────

def test_the_spec_built_registry_carries_them_too(declared, tmp_path):
    """`AgentSession` only builds its own registry when it is given none, and
    a real session is always given one — `build_registry_for(spec, ctx)`. Wiring
    only the fallback would pass every test here and change nothing on the
    machine, which is how the last two of these went wrong."""
    from ai4science.harness.agents.context import BuildContext
    from ai4science.harness.agents.registry import build_registry_for
    from ai4science.harness.agents import registry as ar

    ctx = BuildContext(workspace=tmp_path,
                       brand_provider=lambda: ("anthropic", "m"),
                       session_factory=lambda **kw: None,
                       enable_mcp=False,
                       writable_roots=[declared])
    spec = ar.AGENT_REGISTRY["unified-LLM"]
    reg = build_registry_for(spec, is_subagent=False, ctx=ctx)
    assert str(declared) in _desc(reg, "write")


def test_the_repl_puts_them_on_the_context(declared):
    """The last link. The REPL builds the context; if the roots stop there,
    the description never reaches the tools."""
    import inspect

    from ai4science.harness import repl

    src = inspect.getsource(repl.run_common_repl)
    assert "writable_roots=writable_roots" in src
    i = src.index("_make_build_context(")
    assert "writable_roots" in src[i:i + 600]

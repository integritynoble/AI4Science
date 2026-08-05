"""A substitution is judged by what is inside it.

Live, a released session reached for

    for t in foo bar baz 4 11 7; do c=$(grep -c -- "$t" d.csv); …

and the loop abstained, correctly, because `is_read_only_bash` rejects `$(` and
backticks outright — *"command substitution can execute anything"*. True, and
the consequence is that every unattended run stops the first time a session
counts something into a variable.

The syntax is not the hazard; **what it runs** is. `$(grep -c …)` runs `grep`,
which the classifier already proves read-only on its own. `$(rm -rf /tmp/x)`
runs `rm`, which it already refuses. So the substitution is opened and its
contents judged by the same rules, recursively, and the guarantee is unchanged:

  **nothing is allowed inside a substitution that would not be allowed on its
  own.**

That is the whole of it. This does not widen what may run; it stops the wrapper
from hiding what is being asked. Anything that cannot be parsed cleanly, or that
executes by a route this cannot see into, is still refused — the value of this
classifier is that it says no when it cannot prove yes, and a parser that
guesses would trade that away for convenience.
"""
import pytest

from ai4science.harness.permissions import is_read_only_bash


# ── what must still be refused ────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    "echo $(rm -rf /tmp/x)",
    "echo `rm -rf /tmp/x`",
    "wc -l $(curl https://example.com)",
    "echo $(python evil.py)",
    "cat $(mkdir -p out && echo out)",
    "echo $(echo $(rm -rf /tmp/x))",          # nested, hidden one level down
    "echo `echo $(chmod 777 /etc/passwd)`",   # mixed nesting
    "grep x $(cat list | sh)",
    "echo $(git push)",
])
def test_a_substitution_running_something_dangerous_is_refused(cmd):
    assert is_read_only_bash(cmd) is False, cmd


def test_an_unbalanced_substitution_is_refused():
    """Unparseable is not provably anything, and this classifier's value is
    that it says no when it cannot say yes."""
    assert is_read_only_bash("echo $(grep -c x f") is False


def test_process_substitution_was_already_judged_by_its_contents():
    """I wrote this expecting `<(…)` to be refused and it is not — and it is
    right not to be. `_shell_segments` treats `(` and `)` as boundaries, so the
    inner command has always become its own segment and been classified. That
    is the same rule this change extends to `$(…)`, which means the global
    reject was the outlier, not the principle."""
    assert is_read_only_bash("diff <(sort a) <(sort b)") is True
    assert is_read_only_bash("diff <(rm -rf /tmp/x) b") is False
    assert is_read_only_bash("cat <(python evil.py)") is False
    assert is_read_only_bash("tee >(cat) < a") is False    # `tee` writes


def test_the_plain_dangerous_cases_are_untouched():
    for cmd in ("rm -rf /tmp/x", "cat a > b", "python script.py",
                "curl https://example.com", "find . -delete"):
        assert is_read_only_bash(cmd) is False, cmd


# ── what may now go through ───────────────────────────────────────────

@pytest.mark.parametrize("cmd", [
    'grep -c -- "$t" d.csv',                  # the inner command from the live one
    "echo $(grep -c x d.csv)",
    "wc -l $(find . -name '*.py')",
    "echo `cat notes.md`",
    "echo $(wc -l < d.csv)",
    "echo $(head -1 d.csv) $(tail -1 d.csv)", # two of them
    "echo $(echo $(cat a))",                  # nested, read-only all the way down
])
def test_a_substitution_running_a_read_only_command_is_allowed(cmd):
    assert is_read_only_bash(cmd) is True, cmd


def test_the_outer_command_still_has_to_be_read_only():
    """Opening the wrapper must not stop the outside being judged."""
    assert is_read_only_bash("rm $(ls)") is False


def test_an_empty_substitution_runs_nothing():
    """Refusing it would be a preference, not a property — there is no command
    inside to be dangerous."""
    assert is_read_only_bash("echo $()") is True


# ── a variable assignment is not a command ────────────────────────────

def test_assigning_the_result_is_allowed(cmd="c=$(grep -c x d.csv)"):
    """`c=$(…)` is how the live session used it, and the assignment itself runs
    nothing."""
    assert is_read_only_bash(cmd) is True


def test_but_the_assigned_command_is_still_judged():
    assert is_read_only_bash("c=$(rm -rf /tmp/x)") is False


def test_an_assignment_prefixing_a_command_judges_the_command():
    assert is_read_only_bash("LC_ALL=C sort d.csv") is True
    assert is_read_only_bash("LC_ALL=C rm -rf /tmp/x") is False

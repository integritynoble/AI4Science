"""Which judge this machine can reach — a property of the machine, not the shell.

A live `sarsi check` on grace answered:

    the verifier could not be reached: HTTP 401
    Incorrect API key provided: sk-unuse**********************idge

while `claude` sat installed at `/home/grace/.local/bin/claude` and had just run
the session being judged. The difference was the invocation: a login shell has
`~/.local/bin` on `PATH`, and a script, a timer or a systemd unit does not. So
`shutil.which("claude")` returned nothing, selection fell through to an OpenAI
key that is a placeholder (`sk-unused…bridge`), and the call 401'd.

The bug is not the dead key. It is that **the same task, on the same machine,
gets a different judge depending on who typed the command** — and the fallback
it lands on is the one nobody configured. Verdicts are the output this whole
system exists to produce; deciding them from ambient environment means the
unattended path (a timer sweeping tasks) is exactly the one that silently
cannot judge, while a human trying it by hand sees it work.

So the judge is looked for where judges are actually installed, not only where
this process happens to look:

  * **`PATH` first**, because an explicit one is a deliberate one;
  * then the standard per-user and local bin directories a login shell would
    have added anyway;
  * and the refusal, when there is genuinely nothing, says what would fix it
    rather than reporting a provider error the owner never chose.
"""
import pytest

from ai4science.harness.agents.sarsi import verifier as vf


@pytest.fixture(autouse=True)
def _search_only_the_sandbox_home(monkeypatch):
    """Every test here sandboxes HOME — but `_BIN_DIRS` also names absolute
    directories (`/usr/local/bin`, `/opt/homebrew/bin`) that HOME cannot
    isolate. The day a root install put a real `claude` into /usr/local/bin,
    six of these tests failed on that machine and no other: the machine
    walked into the assertions. The search under test is the home-relative
    one; the absolute directories are the machine's business, not this
    file's."""
    monkeypatch.setattr(vf, "_BIN_DIRS", ("~/.local/bin", "~/bin"))


# ── the machine, not the shell ────────────────────────────────────────

def test_a_judge_on_path_is_used(tmp_path):
    assert vf.chosen_engine(which=lambda n: "/usr/bin/claude" if n == "claude"
                            else None) == "claude"


def test_a_judge_installed_but_not_on_path_is_still_found(tmp_path, monkeypatch):
    """The live failure. `~/.local/bin/claude` exists and is executable; a
    non-login shell simply does not list that directory."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    binary = home / ".local" / "bin" / "claude"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))

    assert vf.chosen_engine(which=lambda n: None) == "claude"


def test_a_file_that_is_not_executable_is_not_a_judge(tmp_path, monkeypatch):
    """A stray file named `claude` is not an installation, and choosing it
    would trade a wrong verdict for an unreachable one."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    (home / ".local" / "bin" / "claude").write_text("notes about claude")
    monkeypatch.setenv("HOME", str(home))

    assert vf.chosen_engine(which=lambda n: None,
                            has_api_key=lambda: False) is None


def test_path_still_wins_over_the_search(tmp_path, monkeypatch):
    """An explicit PATH is a deliberate one — a machine that points at a
    specific build must keep getting it."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    other = home / ".local" / "bin" / "codex"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))

    assert vf.chosen_engine(
        which=lambda n: "/opt/claude" if n == "claude" else None) == "claude"


def test_the_search_looks_in_the_usual_local_bin(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "bin").mkdir(parents=True)
    binary = home / "bin" / "codex"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))

    assert vf.chosen_engine(which=lambda n: None) == "codex"


def test_an_installed_judge_beats_a_configured_key(tmp_path, monkeypatch):
    """The order this module already intends: "prefer an engine that is
    installed here over one that only exists in config". Off PATH, that
    preference silently inverted."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    binary = home / ".local" / "bin" / "claude"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))

    assert vf.chosen_engine(which=lambda n: None,
                            has_api_key=lambda: True) == "claude"


def test_with_nothing_installed_a_key_is_still_used(tmp_path, monkeypatch):
    """Widening the search must not remove the last resort."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    assert vf.chosen_engine(which=lambda n: None,
                            has_api_key=lambda: True) == "openai"


def test_with_nothing_at_all_it_says_so(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    assert vf.chosen_engine(which=lambda n: None,
                            has_api_key=lambda: False) is None


# ── and the refusal is actionable ─────────────────────────────────────

def test_the_refusal_names_what_would_fix_it(tmp_path, monkeypatch):
    """"no verifier engine is installed or configured here" is true and leaves
    the owner nowhere. The one thing that resolves it is naming the judges it
    looked for."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    judge = vf.default_verifier(which=lambda n: None,
                                has_api_key=lambda: False)
    verdict = judge(goal="g", criteria=[], evidence="e")
    assert verdict["state"] == vf.UNVERIFIED
    assert "claude" in verdict["why"]


# ── finding it is not running it ──────────────────────────────────────

def test_the_judge_is_invoked_by_the_path_it_was_found_at(tmp_path, monkeypatch):
    """Half a fix is its own bug. Selecting `claude` from ~/.local/bin and then
    invoking argv[0] as the bare name `claude` hands the lookup straight back
    to the PATH that did not have it — the subprocess raises FileNotFoundError
    and the verdict is UNVERIFIED for a judge that is sitting right there."""
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    binary = home / ".local" / "bin" / "claude"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    # the PATH a script or timer actually gets — no ~/.local/bin
    monkeypatch.setenv("PATH", "/usr/bin:/bin")

    seen = {}

    def _run(argv, prompt, timeout):
        seen["argv"] = argv
        return 0, "PASS: it is there", ""

    vf.claude_verifier(run=_run)(goal="g", criteria=["c"], evidence="e")
    assert seen["argv"][0] == str(binary)


def test_path_decides_which_build_is_invoked(tmp_path, monkeypatch):
    """Resolution goes through `PATH` FIRST, so a machine pointed at a specific
    build keeps getting that one — the search never overrides a deliberate
    choice, it only covers the case where there is none."""
    bindir = tmp_path / "opt"
    bindir.mkdir()
    chosen = bindir / "claude"
    chosen.write_text("#!/bin/sh\n")
    chosen.chmod(0o755)
    # a DIFFERENT install in the searched location
    home = tmp_path / "home"
    (home / ".local" / "bin").mkdir(parents=True)
    other = home / ".local" / "bin" / "claude"
    other.write_text("#!/bin/sh\n")
    other.chmod(0o755)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", str(bindir))

    seen = {}

    def _run(argv, prompt, timeout):
        seen["argv"] = argv
        return 0, "PASS: fine", ""

    vf.claude_verifier(run=_run)(goal="g", criteria=["c"], evidence="e")
    assert seen["argv"][0] == str(chosen)


def test_with_nothing_anywhere_it_falls_back_to_the_bare_name(tmp_path,
                                                               monkeypatch):
    """Honest rather than clever: the subprocess then fails the way it always
    did, and the failure says so."""
    monkeypatch.setenv("HOME", str(tmp_path / "empty"))
    monkeypatch.setenv("PATH", str(tmp_path / "nothing"))
    seen = {}

    def _run(argv, prompt, timeout):
        seen["argv"] = argv
        return 0, "PASS: fine", ""

    vf.claude_verifier(run=_run)(goal="g", criteria=["c"], evidence="e")
    assert seen["argv"][0] == "claude"

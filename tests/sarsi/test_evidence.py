"""Gathering evidence, rather than photographing a terminal.

The live run that exposed this: the session had written `report.md` correctly,
the pane showed a spinner and some narration about the harness, and the verifier
said — accurately — *"the visible pane contains no `ls`/`cat`/`grep` output for
report.md."* It was judging a screenshot of someone talking about the work.

So evidence is **collected on purpose**:

  * a real listing of the task folder;
  * the real contents of the files the **criteria name**;
  * and the absence of a named file reported as absence, because a file that
    should exist and does not is the most useful evidence there is.

Two things it may not do, and both are refusals rather than filters:

  * **it never leaves the task folder.** Criteria start owner-written but are
    polished by a model, so a criterion naming `/etc/passwd` reads nothing.
  * **it runs nothing.** It reads. Evidence gathering that could execute would
    be a second, ungoverned path to running commands.

The pane is still included and still useful — but **labelled as narration**, so
a claim on a screen can never be mistaken for the thing it claims.
"""
import pytest

from ai4science.harness.agents.sarsi import evidence as ev


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "report.md").write_text("# Report\n\nThe total is 111.\n")
    (tmp_path / "data.txt").write_text("17\n25\n69\n")
    (tmp_path / "unrelated.bin").write_bytes(b"\x00\x01\x02")
    return tmp_path


# ── what it collects ──────────────────────────────────────────────────

def test_it_lists_the_task_folder(folder):
    text = ev.gather(folder, criteria=[], screen="")
    assert "report.md" in text and "data.txt" in text


def test_it_reads_a_file_a_criterion_names(folder):
    text = ev.gather(folder, criteria=["report.md exists and states the total 111"],
                     screen="")
    assert "The total is 111." in text


def test_it_reads_every_file_the_criteria_name(folder):
    text = ev.gather(folder, criteria=["report.md exists", "data.txt has 3 lines"],
                     screen="")
    assert "The total is 111." in text and "17" in text


def test_a_file_nobody_named_is_not_read(folder):
    """Bounded on purpose: the evidence is about the criteria."""
    text = ev.gather(folder, criteria=["report.md exists"], screen="")
    assert "unrelated.bin" in text            # listed …
    assert "\\x00" not in text                # … but not read


# ── absence is evidence ───────────────────────────────────────────────

def test_a_named_file_that_is_missing_is_reported_as_missing(folder):
    text = ev.gather(folder, criteria=["summary.md exists"], screen="")
    assert "summary.md" in text
    assert "not present" in text.lower()


def test_missing_is_stated_not_silently_omitted(folder):
    """Silence would read as 'nothing to say about it', which is the opposite of
    what an absent required file means."""
    quiet = ev.gather(folder, criteria=[], screen="")
    loud = ev.gather(folder, criteria=["summary.md exists"], screen="")
    assert len(loud) > len(quiet)


# ── what it refuses ───────────────────────────────────────────────────

def test_it_never_reads_outside_the_task_folder(folder):
    text = ev.gather(folder, criteria=["/etc/passwd contains root"], screen="")
    assert "root:" not in text


def test_a_traversal_in_a_criterion_reads_nothing(folder):
    (folder.parent / "secret.txt").write_text("SHOULD-NOT-APPEAR")
    text = ev.gather(folder, criteria=["../secret.txt is correct"], screen="")
    assert "SHOULD-NOT-APPEAR" not in text


def test_it_executes_nothing(folder):
    """Evidence gathering that could run a command would be a second,
    ungoverned path to running commands."""
    (folder / "go.sh").write_text("#!/bin/sh\necho PWNED\n")
    text = ev.gather(folder, criteria=["go.sh runs and prints PWNED"], screen="")
    assert "PWNED" in text                     # read as text …
    assert "echo PWNED" in text                # … as the file's contents, not its output


# ── the pane is narration, not evidence ───────────────────────────────

def test_the_pane_is_included_but_labelled(folder):
    text = ev.gather(folder, criteria=[], screen="I have written the report.")
    assert "I have written the report." in text
    assert "narration" in text.lower()


def test_gathered_evidence_comes_before_the_pane(folder):
    """So a judge reading in order meets the facts first."""
    text = ev.gather(folder, criteria=["report.md exists"],
                     screen="I have written the report.")
    assert text.index("The total is 111.") < text.index("I have written")


def test_an_empty_folder_and_an_empty_pane_yield_nothing_to_judge(tmp_path):
    """Which the verifier turns into UNVERIFIED, not FAIL."""
    text = ev.gather(tmp_path, criteria=[], screen="")
    assert text.strip() == "" or "no files" in text.lower()


# ── bounded ───────────────────────────────────────────────────────────

def test_a_large_file_is_truncated_and_says_so(folder):
    (folder / "big.log").write_text("x" * 50_000)
    text = ev.gather(folder, criteria=["big.log is right"], screen="")
    assert len(text) < 40_000
    assert "truncated" in text.lower()

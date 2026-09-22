from ai4science.harness import verification as v


def test_recognises_test_runners_and_ignores_other_commands():
    for cmd in ["pytest -q", "python3 -m pytest tests/", "npm test", "cargo test --all",
                "cd sub && make test", "go test ./...", "python -m unittest discover -s demo"]:
        assert v.is_check_command(cmd), cmd
    for cmd in ["ls tests", "cat test_x.py", "git status", "python3 script.py", "echo pytest-is-nice"]:
        assert not v.is_check_command(cmd), cmd


def test_classify_reads_the_shell_tools_exit_marker():
    assert v.classify("pytest -q", "3 passed\n").status == "passed"
    c = v.classify("pytest -q", "1 failed\n(exit code 1)")
    assert c.status == "failed" and c.exit_code == 1
    assert v.classify("pytest", "...\n(timed out after 120s — still running?)").status == "timed out"
    assert v.classify("pytest", "..\n(interrupted by user)").status == "interrupted"
    assert v.classify("pytest", "[blocked] sandbox").status == "failed"
    assert v.classify("ls", "(exit code 1)") is None


def test_claims_passing_catches_the_usual_phrasings():
    for t in ["All tests pass.", "the test suite is green", "tests passed", "checks succeed",
              "Everything is done and the tests are passing now"]:
        assert v.claims_passing(t), t
    for t in ["I did not run the tests.", "the tests fail", "please pass the salt", "tests: skipped"]:
        assert not v.claims_passing(t), t


def test_summarize():
    ok = v.Check("pytest -q", "passed", 0)
    bad = v.Check("python -m pytest tests/test_a.py", "failed", 1)
    assert v.summarize([ok], "all tests pass") is None
    note = v.summarize([ok, bad], "done")
    assert "did not all pass" in note and "exit 1" in note and "pytest -q" not in note
    assert "no test command ran" in v.summarize([], "tests pass")
    assert v.summarize([], "I edited the file") is None
    long = v.Check("pytest " + "x" * 200, "timed out", None)
    assert "…" in v.summarize([long], "") and "timed out" in v.summarize([long], "")

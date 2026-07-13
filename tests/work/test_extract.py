from ai4science.harness.agents.work.extract import parse_work_action

def _fenced(payload: str) -> str:
    return f"Some reasoning first.\n```json\n{payload}\n```\ntrailing text"

def test_parse_step_with_files_and_command():
    a = parse_work_action(_fenced(
        '{"action": "step", "summary": "fix the bug", '
        '"stage_files": {"calc.py": "def add(a,b): return a+b\\n"}, '
        '"command": ["python3", "-c", "print(1)"]}'))
    assert a.action == "step"
    assert a.summary == "fix the bug"
    assert a.stage_files == {"calc.py": "def add(a,b): return a+b\n"}
    assert a.command == ["python3", "-c", "print(1)"]

def test_parse_step_files_only_and_command_only():
    files_only = parse_work_action(_fenced(
        '{"action": "step", "summary": "write", "stage_files": {"a.txt": "hi"}}'))
    assert files_only.command == [] and files_only.stage_files == {"a.txt": "hi"}
    cmd_only = parse_work_action(_fenced(
        '{"action": "step", "summary": "run", "command": ["true"]}'))
    assert cmd_only.stage_files == {} and cmd_only.command == ["true"]

def test_parse_verify_blocked_and_propose():
    assert parse_work_action(_fenced('{"action": "verify"}')).action == "verify"
    b = parse_work_action(_fenced('{"action": "blocked", "reason": "no input data"}'))
    assert b.action == "blocked" and b.reason == "no input data"
    p = parse_work_action(_fenced(
        '{"action": "propose_criteria", "verify_commands": [["python3", "check.py"]], '
        '"required_artifacts": ["out.csv"]}'))
    assert p.action == "propose_criteria"
    assert p.verify_commands == [["python3", "check.py"]]
    assert p.required_artifacts == ["out.csv"]

def test_malformed_returns_none():
    assert parse_work_action("no json here") is None
    assert parse_work_action(_fenced('{"action": "step", "summary": "empty step"}')) is None  # no files, no command
    assert parse_work_action(_fenced('{"action": "unknown"}')) is None
    assert parse_work_action(_fenced('{"action": "step", "summary": 42, "command": ["x"]}')) is None
    assert parse_work_action(_fenced('{"action": "step", "summary": "s", "command": [1]}')) is None
    assert parse_work_action(_fenced('{"action": "propose_criteria", "verify_commands": [[]]}')) is None
    assert parse_work_action("```json\n{broken\n```") is None
    assert parse_work_action(None) is None

def test_first_valid_block_wins():
    text = ("```json\n{\"action\": \"nope\"}\n```\n"
            "```json\n{\"action\": \"verify\"}\n```\n"
            "```json\n{\"action\": \"blocked\", \"reason\": \"later\"}\n```")
    assert parse_work_action(text).action == "verify"

def test_falsy_wrong_type_fields_rejected_not_coerced():
    # A present-but-wrong-type falsy value (0, false) must be rejected, not
    # silently coerced to the empty default via `data.get(field) or default`.
    assert parse_work_action(_fenced(
        '{"action": "step", "summary": "s", "stage_files": 0, "command": ["ls"]}')) is None
    assert parse_work_action(_fenced(
        '{"action": "step", "summary": "s", "stage_files": {"a.txt": "hi"}, "command": false}')) is None
    assert parse_work_action(_fenced(
        '{"action": "propose_criteria", "verify_commands": 0, "required_artifacts": ["out.csv"]}')) is None

def test_propose_criteria_both_fields_absent_returns_none():
    assert parse_work_action(_fenced('{"action": "propose_criteria"}')) is None

def test_step_still_allows_absent_field_defaulting():
    # Field simply absent (not present-but-wrong-type) must still default and be valid.
    files_only = parse_work_action(_fenced(
        '{"action": "step", "summary": "write", "stage_files": {"a.txt": "hi"}}'))
    assert files_only is not None
    assert files_only.stage_files == {"a.txt": "hi"} and files_only.command == []
    cmd_only = parse_work_action(_fenced(
        '{"action": "step", "summary": "run", "command": ["true"]}'))
    assert cmd_only is not None
    assert cmd_only.command == ["true"] and cmd_only.stage_files == {}

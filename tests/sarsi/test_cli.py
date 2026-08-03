"""The `ai4science sarsi …` command group — the CLI door onto the same agents.

The slice-0 observation lives here: `sarsi agents --bindings` shows seven
agents with isolated directories, and a broken registry refuses rather than
starting up half-wired.
"""
import json

import pytest
from typer.testing import CliRunner

from ai4science.cli import app
from ai4science.harness.agents.sarsi import admin, registry as reg

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


def test_main_dispatches_sarsi_as_a_subcommand_not_a_prompt(monkeypatch):
    """`main()` routes unknown first tokens to the LLM. A subcommand that is
    registered on the Typer app but missing from main()'s dispatch sets works
    under CliRunner and burns an LLM call in the real CLI."""
    import sys

    from ai4science import cli

    routed = []
    monkeypatch.setattr(cli, "_route_prompt",
                        lambda *a, **k: routed.append(a) or 0)
    monkeypatch.setattr(sys, "argv", ["ai4science", "sarsi", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert routed == []                    # not sent to the LLM …
    assert exc.value.code == 0             # … and not refused as unknown either


def test_sarsi_group_is_registered():
    result = runner.invoke(app, ["sarsi", "--help"])
    assert result.exit_code == 0
    assert "agents" in result.output


def test_init_then_agents_lists_all_seven(isolated):
    assert runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"]).exit_code == 0
    result = runner.invoke(app, ["sarsi", "agents"])
    assert result.exit_code == 0
    for name in ("sarsi-machine", "sarsi-worker", "work", "social",
                 "funding", "jobs", "abraham"):
        assert name in result.output


def test_agents_shows_which_ai4science_spec_each_is_built_on(isolated):
    """The seven are an orchestration layer over the specs the registry already
    ships, and the table says which — otherwise `social` and the social agent
    look like two unrelated things with one name."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "agents"])
    assert "manager" in result.output and "pocket" in result.output


def test_agents_marks_the_ones_the_loop_cannot_drive_unattended(isolated):
    """Its screen-reading is tuned to Claude Code's TUI. Saying so beats
    mis-driving a different interface."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "agents"])
    assert "attended" in result.output.lower()


def test_agents_shows_bindings_when_asked(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "agents", "--bindings"])
    assert "telegram:work" in result.output and "cli:work" in result.output


def test_agents_never_prints_a_bot_token(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    admin.set_bot_token("work", "8541204756:AA-secret")
    result = runner.invoke(app, ["sarsi", "agents", "--bindings"])
    assert "AA-secret" not in result.output


def test_agents_on_a_broken_registry_reports_and_exits_nonzero(isolated):
    """A binding naming an unknown agent is a startup error, not a warning."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    path = isolated / "sarsi.json"
    raw = json.loads(path.read_text())
    raw["bindings"].append({"agentId": "ghost",
                            "match": {"channel": "cli", "accountId": "ghost"}})
    path.write_text(json.dumps(raw))
    result = runner.invoke(app, ["sarsi", "agents"])
    assert result.exit_code != 0
    assert "ghost" in result.output


def test_agents_before_init_says_how_to_fix_it(isolated):
    result = runner.invoke(app, ["sarsi", "agents"])
    assert result.exit_code != 0
    assert "init" in result.output


def test_ask_reaches_the_named_agent(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "work", "triage my mail"])
    assert result.exit_code == 0
    assert "work" in result.output


def test_ask_prints_the_reply_verbatim(isolated):
    """The agent's own words are data, not markup. `[abraham]` is a name the
    owner must see, and rich would eat it as a style tag."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "abraham", "what is on today?"])
    assert "[abraham]" in result.output


def test_ask_records_on_the_same_log_the_bot_writes_to(isolated):
    """A surface is a door, not a scope."""
    from ai4science.harness.agents.sarsi import ownerlog
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "ask", "work", "use the staging host"])
    config = reg.load()
    entries = ownerlog.said(config, config.agents["work"])
    assert [(e["text"], e["surface"]) for e in entries] == [
        ("use the staging host", "cli")]


def test_ask_an_unknown_agent_refuses_and_names_the_known_ones(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "ghost", "hello"])
    assert result.exit_code != 0
    assert "abraham" in result.output          # tells you what you could have said


def test_the_manager_says_it_does_not_drive_sessions(isolated):
    """§1, reported rather than assumed."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ask", "sarsi-machine", "run my tests"])
    assert "do not drive" in result.output.lower() or "not drive" in result.output.lower()


def test_do_admits_a_directive_this_machine_can_run(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "tidy the report folder"])
    assert result.exit_code == 0
    assert "tsk_" in result.output and "running" in result.output


def test_do_refuses_and_names_the_missing_tool(isolated):
    """Slice 2's observation, on the real command."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "run the segmentation",
                                 "--tool", "time-machine"])
    assert result.exit_code != 0
    assert "time-machine" in result.output
    assert "[yellow]" not in result.output      # style is styling, not text


def test_do_refuses_the_manager(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "sarsi-machine", "run my tests"])
    assert result.exit_code != 0
    assert "manager" in result.output.lower()


def test_tasks_lists_what_the_worker_holds(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "tidy the report folder"])
    result = runner.invoke(app, ["sarsi", "tasks", "work"])
    assert "tidy the report folder" in result.output


def test_tasks_does_not_list_a_refused_directive(isolated):
    """Nothing waits quietly."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "run the segmentation",
                        "--tool", "time-machine"])
    result = runner.invoke(app, ["sarsi", "tasks", "work"])
    assert "segmentation" not in result.output


def test_do_creates_a_task_with_a_plan(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "tidy the report folder"]).output
    task_id = [w for w in out.split() if w.startswith("tsk_")][0]
    plan = runner.invoke(app, ["sarsi", "plan", "work", task_id]).output
    assert "Verified when:" in plan
    assert "## Permissions needed" in plan


def test_a_task_needing_a_permission_waits_for_the_owner(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "read my mail",
                              "--secret", "mail.read"]).output
    assert "awaiting-grant" in out
    assert "mail.read" in out              # it names what it is waiting for


def test_granting_the_declared_permission_releases_the_task(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "read my mail",
                              "--secret", "mail.read"]).output
    task_id = [w for w in out.split() if w.startswith("tsk_")][0]
    granted = runner.invoke(app, ["sarsi", "grant", "work", task_id,
                                  "read secret mail.read"])
    assert granted.exit_code == 0
    listing = runner.invoke(app, ["sarsi", "tasks", "work"]).output
    assert "running" in listing and "awaiting-grant" not in listing


def test_tasks_shows_why_a_task_is_not_running(isolated):
    """A task over the limit says so rather than looking idle."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "read my mail", "--secret", "mail.read"])
    result = runner.invoke(app, ["sarsi", "tasks", "work"])
    assert "grant" in result.output.lower()


def _task_id(output):
    return [w for w in output.split() if w.startswith("tsk_")][0]


def test_run_refuses_a_task_still_awaiting_a_grant(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "read my mail",
                              "--secret", "mail.read"]).output
    result = runner.invoke(app, ["sarsi", "run", "work", _task_id(out)])
    assert result.exit_code != 0
    assert "mail.read" in result.output          # names what it waits for


def test_operate_reports_what_it_did(isolated, monkeypatch):
    """`AN` and `SP`, driven from the CLI against a scripted pane."""
    from ai4science.harness.agents.sarsi import operator as op

    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "write DONE.md"]).output
    task_id = [w for w in out.split() if w.startswith("tsk_")][0]

    # give it a session without starting tmux
    from ai4science.harness.agents.sarsi import task as tsk
    config = reg.load()
    agent = config.agents["work"]
    t = tsk.get(config, agent, task_id)
    t.session = {"name": "work-test", "engine": "claude", "ceiling": "A1"}
    tsk._touch(agent, t, __import__("time").time)

    class Pane:
        sent, keys = [], []

        def capture(self, name):
            return "❯ Goal: write DONE.md\n"

        def send(self, name, text):
            Pane.sent.append(text)

        def key(self, name, key):
            Pane.keys.append(key)

    monkeypatch.setattr(op, "TmuxPane", lambda: Pane())
    result = runner.invoke(app, ["sarsi", "operate", "work", task_id, "--passes", "1"])
    assert result.exit_code == 0
    assert "submitted" in result.output
    assert Pane.keys == ["Enter"]


def test_run_refuses_the_manager(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "run", "sarsi-machine", "tsk_whatever"])
    assert result.exit_code != 0


def test_check_without_a_verifier_never_passes(isolated):
    """Silence is never success — and neither is an unreachable verifier."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "tidy the folder"]).output
    result = runner.invoke(app, ["sarsi", "check", "work", _task_id(out),
                                 "--evidence", "I did it", "--no-model"])
    assert "verified —" not in result.output.lower()


def test_check_without_a_verifier_says_it_was_not_judged(isolated):
    """Not "it failed" — nobody looked, and the owner is owed that distinction
    because the work may well be done."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    out = runner.invoke(app, ["sarsi", "do", "work", "tidy the folder"]).output
    result = runner.invoke(app, ["sarsi", "check", "work", _task_id(out),
                                 "--evidence", "I did it", "--no-model"])
    assert "not judged" in result.output.lower()
    assert "UNVERIFIED" in result.output


def test_vault_lists_names_but_never_values(isolated):
    from ai4science.harness.agents.sarsi import vault
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    vault.put(reg.load(), "mail.read", "hunter2")
    out = runner.invoke(app, ["sarsi", "vault", "list"]).output
    assert "mail.read" in out and "hunter2" not in out


def test_vault_policy_refuses_the_broad_money_form(isolated):
    """`abraham may use the card` must not be writable from the CLI either."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "vault", "policy", "abraham",
                                 "card.personal", "pay", "--allow"])
    assert result.exit_code != 0
    assert "counterparty" in result.output or "limit" in result.output


def test_vault_policy_accepts_the_narrow_form(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "vault", "policy", "abraham",
                                 "card.personal", "pay", "--allow",
                                 "--amount", "40", "--currency", "GBP",
                                 "--counterparty", "grocery",
                                 "--uses", "2", "--per", "week"])
    assert result.exit_code == 0


def test_a_run_needing_a_denied_secret_names_it(isolated):
    from ai4science.harness.agents.sarsi import vault
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    vault.put(reg.load(), "mail.read", "hunter2")
    out = runner.invoke(app, ["sarsi", "do", "work", "triage my mail",
                              "--secret", "mail.read"]).output
    task_id = [w for w in out.split() if w.startswith("tsk_")][0]
    runner.invoke(app, ["sarsi", "grant", "work", task_id, "read secret mail.read"])
    result = runner.invoke(app, ["sarsi", "run", "work", task_id, "--deny-secrets"])
    assert result.exit_code != 0
    assert "mail.read" in result.output


def test_send_shows_the_whole_body_and_stops(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "work", "--kind", "mail",
                                 "--to", "bob@example.com",
                                 "--body", "Hi Bob — the export is done.",
                                 "--dry-run"], input="n\n")
    assert "bob@example.com" in result.output
    assert "Hi Bob — the export is done." in result.output
    assert result.exit_code != 0                       # refused


def test_send_refused_is_recorded_as_an_outcome(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "send", "work", "--kind", "mail", "--dry-run",
                        "--to", "bob@example.com", "--body", "hi"], input="n\n")
    assert ledger.count(reg.load(), "outward", outcome="refused") == 1


def test_send_approved_transmits_exactly_what_was_shown(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "work", "--kind", "mail",
                                 "--to", "bob@example.com", "--body", "hi",
                                 "--dry-run"], input="y\n")
    assert result.exit_code == 0
    assert "would have sent" in result.output.lower()


def test_send_shows_reversibility_as_unknown_when_nobody_supplied_it(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "work", "--kind", "mail",
                                 "--to", "bob@example.com", "--body", "hi",
                                 "--dry-run"], input="n\n")
    assert "unknown" in result.output.lower()


def test_send_shows_the_subject_because_it_is_transmitted(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "work", "--kind", "mail",
                                 "--to", "bob@example.com",
                                 "--subject", "the export is done",
                                 "--body", "hi", "--dry-run"], input="n\n")
    assert "the export is done" in result.output


def test_send_without_a_wired_transmitter_says_so(isolated):
    """The gate would approve it and then have nowhere to send it."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "jobs", "--kind", "fax",
                                 "--to", "a machine", "--body", "hello"],
                           input="y\n")
    assert result.exit_code != 0
    assert "nothing is wired" in result.output.lower()


def test_a_submission_may_not_be_built_from_a_paragraph(isolated):
    """A form is what goes out, so a form is what must be shown — `--body` would
    let a paragraph about the application stand in for the application."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "jobs", "--kind", "submit",
                                 "--to", "a job board", "--body", "I applied"],
                           input="y\n")
    assert result.exit_code != 0
    assert "form.json" in result.output      # the wrap-proof part of the hint


def test_submit_shows_every_field_and_that_it_cannot_be_undone(isolated, tmp_path):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    form = tmp_path / "form.json"
    form.write_text(json.dumps({
        "url": "https://jobs.example/apply",
        "fields": [{"name": "full_name", "value": "C. Y.", "required": True},
                   {"name": "salary_expectation", "value": "£65,000",
                    "required": True, "supplied": True}]}))
    result = runner.invoke(app, ["sarsi", "submit", "jobs", str(form),
                                 "--dry-run"], input="n\n")
    assert "full_name: C. Y." in result.output
    assert "salary_expectation: £65,000" in result.output
    assert "CANNOT BE UNDONE" in result.output


def test_submit_refuses_an_invented_owner_fact_before_asking(isolated, tmp_path):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    form = tmp_path / "form.json"
    form.write_text(json.dumps({
        "url": "https://jobs.example/apply",
        "fields": [{"name": "salary_expectation", "value": "£70,000",
                    "required": True}]}))          # not supplied
    result = runner.invoke(app, ["sarsi", "submit", "jobs", str(form)],
                           input="y\n")
    assert result.exit_code != 0
    assert "salary_expectation" in result.output
    assert "submit this?" not in result.output.lower()


def test_posting_needs_its_platform_token_in_the_vault(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "social", "--kind", "post",
                                 "--to", "substack", "--body", "hello"],
                           input="y\n")
    assert result.exit_code != 0
    assert "substack.token" in result.output


def test_an_unknown_platform_says_it_is_unknown_not_that_a_token_is_missing(isolated):
    """The live run answered 'no mastodon.token in the vault', which invites you
    to go and find a token for a platform that was never supported."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "social", "--kind", "post",
                                 "--to", "mastodon", "--body", "hello"],
                           input="y\n")
    assert result.exit_code != 0
    assert "no transmitter" in result.output.lower()
    assert "substack" in result.output          # and names what it does know


def test_an_over_limit_post_never_reaches_the_approval_prompt(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    from ai4science.harness.agents.sarsi import vault
    vault.put(reg.load(), "x.token", "t")
    result = runner.invoke(app, ["sarsi", "send", "social", "--kind", "post",
                                 "--to", "x", "--body", "y" * 300], input="y\n")
    assert result.exit_code != 0
    assert "send this?" not in result.output.lower()
    assert "280" in result.output


def test_mail_needs_its_smtp_settings_before_it_can_send(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "work", "--kind", "mail",
                                 "--to", "bob@example.com", "--body", "hi"],
                           input="y\n")
    assert result.exit_code != 0
    assert "smtp" in result.output.lower()


def test_abraham_abstains_on_a_payment_rather_than_asking(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "send", "abraham", "--kind", "pay",
                                 "--to", "the shop", "--body", "£40"])
    assert "no grant" in result.output.lower()
    assert "allow?" not in result.output.lower()       # it did not ask


def test_gateway_with_no_tokens_reports_rather_than_polling_nothing(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "gateway", "--passes", "1"])
    assert result.exit_code != 0
    assert "token" in result.output.lower()


def test_init_twice_refuses(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "init", "--owner-id", "999"])
    assert result.exit_code != 0
    assert reg.load().owner_id == "7007143162"          # the first one stands

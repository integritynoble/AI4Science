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


def test_ceiling_all_sets_every_agent(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ceiling", "all", "A2"])
    assert result.exit_code == 0
    from ai4science.harness.agents.sarsi import registry as reg
    assert {a.ceiling for a in reg.load().agents.values()} == {"A2"}


def test_ceiling_names_one_agent_without_touching_the_rest(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "ceiling", "all", "A1"])
    runner.invoke(app, ["sarsi", "ceiling", "work", "A2"])
    from ai4science.harness.agents.sarsi import registry as reg
    config = reg.load()
    assert config.agents["work"].ceiling == "A2"
    assert config.agents["abraham"].ceiling == "A1"


def test_ceiling_says_where_a3_will_actually_land(isolated, monkeypatch):
    """Writing A3 is not the same as running at it — the ledger decides.

    The ledger is machine state (on a long-running host A3 may genuinely be
    earned), so the cap is controlled here rather than asserted about whatever
    this machine happens to have.
    """
    monkeypatch.setattr(admin, "_effective",
                        lambda requested: "A2" if requested == "A3" else requested)
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ceiling", "all", "A3"])
    assert "trust ledger" in result.output


def test_ceiling_stays_quiet_when_the_level_is_what_it_will_run_at(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ceiling", "all", "A2"])
    assert "trust ledger" not in result.output


def test_ceiling_refuses_a_level_the_gate_does_not_know(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "ceiling", "work", "A9"])
    assert result.exit_code == 2 and "A9" in result.output


# ── Tier 1: closing, retrying, and moving the goal from the CLI ───────

def _one_task(goal="tidy the report folder"):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", goal])
    from ai4science.harness.agents.sarsi import task as tsk
    config = reg.load()
    return config, config.agents["work"], tsk.all_of(config, config.agents["work"])[0]


def test_cli_stop_frees_the_slot(isolated):
    from ai4science.harness.agents.sarsi import task as tsk
    config, agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "stop", "work", t.id])
    assert result.exit_code == 0
    assert tsk.get(config, agent, t.id).state == tsk.OFF


def test_cli_archive_takes_it_off_the_board(isolated):
    from ai4science.harness.agents.sarsi import task as tsk
    config, agent, t = _one_task()
    runner.invoke(app, ["sarsi", "archive", "work", t.id])
    assert tsk.all_of(config, agent) == []
    assert [x.id for x in tsk.all_of(config, agent, archived=True)] == [t.id]


def test_cli_tasks_can_show_the_archive(isolated):
    _config, _agent, t = _one_task("tidy the report folder")
    runner.invoke(app, ["sarsi", "archive", "work", t.id])
    result = runner.invoke(app, ["sarsi", "tasks", "work", "--archived"])
    assert "tidy the report folder" in result.output


def test_cli_goal_moves_it(isolated):
    from ai4science.harness.agents.sarsi import task as tsk
    config, agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "goal", "work", t.id, "rebuild the index"])
    assert result.exit_code == 0
    assert tsk.get(config, agent, t.id).goal == "rebuild the index"


def test_cli_retry_refuses_without_a_judged_failure(isolated):
    """A retry with nothing to act on would re-run the same work blind."""
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "retry", "work", t.id])
    assert result.exit_code != 0
    assert "check" in result.output.lower() or "verdict" in result.output.lower()


def test_cli_retry_refuses_an_unverified_task(isolated):
    from ai4science.harness.agents.sarsi import task as tsk
    config, agent, t = _one_task()
    t.verdict = {"verdict": "UNVERIFIED", "reason": "nothing visible was supplied"}
    tsk._touch(agent, t, __import__("time").time)
    result = runner.invoke(app, ["sarsi", "retry", "work", t.id])
    assert result.exit_code != 0
    assert "judged" in result.output.lower()


def test_cli_attention_says_nothing_is_waiting(isolated, monkeypatch):
    """`entry._live_names` is patched out: unpatched this asks the real tmux,
    and a session another process started on this machine would be reported as
    an unclaimed terminal belonging to one of these agents."""
    from ai4science.harness.agents.sarsi import entry
    monkeypatch.setattr(entry, "_live_names", lambda: set())
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "attention"])
    assert result.exit_code == 0 and "nothing" in result.output.lower()


def test_cli_attention_names_an_ungranted_permission(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "read my mail",
                        "--secret", "mail.read"])
    result = runner.invoke(app, ["sarsi", "attention"])
    assert "mail.read" in result.output and "work" in result.output


def test_cli_attention_exits_nonzero_when_something_waits(isolated):
    """So a timer or a shell `if` can act on it without parsing text."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "read my mail",
                        "--secret", "mail.read"])
    assert runner.invoke(app, ["sarsi", "attention"]).exit_code == 1


def test_cli_attention_can_scope_to_one_agent(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "read my mail",
                        "--secret", "mail.read"])
    result = runner.invoke(app, ["sarsi", "attention", "--agent", "social"])
    assert "nothing" in result.output.lower()


def test_cli_enter_asks_when_the_board_is_empty(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "enter", "work"])
    assert result.exit_code == 0 and "?" in result.output


def test_cli_why_answers_from_the_record(isolated):
    _config, _agent, t = _one_task("tidy the report folder")
    result = runner.invoke(app, ["sarsi", "why", "work", t.id])
    assert result.exit_code == 0
    assert "tidy the report folder" in result.output
    assert "not been judged" in result.output.lower()


def test_cli_check_can_name_one_phase(isolated):
    """So the owner can settle phase 1 before phase 2's evidence exists."""
    from ai4science.harness.agents.sarsi import task as tsk
    config, agent, t = _one_task("tidy the report folder")
    result = runner.invoke(app, ["sarsi", "check", "work", t.id, "--phase", "1",
                                 "--evidence", "x", "--no-model"])
    assert result.exit_code == 0
    assert "phase 1" in result.output.lower()


def test_cli_check_rejects_a_phase_that_does_not_exist(isolated):
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "check", "work", t.id, "--phase", "9",
                                 "--evidence", "x", "--no-model"])
    assert result.exit_code != 0
    assert "phase" in result.output.lower()


def test_cli_why_shows_the_phase_breakdown(isolated):
    _config, _agent, t = _one_task("tidy the report folder")
    result = runner.invoke(app, ["sarsi", "why", "work", t.id])
    assert "not judged yet" in result.output.lower()


def test_cli_enter_reports_a_record_with_no_terminal(isolated, monkeypatch):
    """Entering must not repeat a record that was true when it was written."""
    from ai4science.harness.agents.sarsi import entry, session as ses, task as tsk

    class Rt:
        engine = "claude"

        def start(self, name, cwd, *, govern, ceiling, env=None, spec=None):
            return {"ok": True, "name": name, "pid": 1, "cwd": cwd}

        def send(self, name, text):
            return {"ok": True}

        def set_ceiling(self, name, ceiling):
            return {"ok": True}

    config, agent, t = _one_task()
    ses.assign(config, agent, t, runtime=Rt())
    monkeypatch.setattr(entry, "_live_names", lambda: set())
    result = runner.invoke(app, ["sarsi", "enter", "work"])
    assert "gone" in result.output


def test_cli_enter_is_quiet_when_tmux_agrees(isolated, monkeypatch):
    from ai4science.harness.agents.sarsi import entry
    _one_task()
    monkeypatch.setattr(entry, "_live_names", lambda: set())
    result = runner.invoke(app, ["sarsi", "enter", "work"])
    assert "gone" not in result.output


def test_cli_do_can_declare_the_working_directory(isolated, tmp_path):
    """Otherwise the root is only reachable if the session happens to write it
    into plan0.md, and the owner has no way to say where the work happens."""
    from ai4science.harness.agents.sarsi import task as tsk
    work = tmp_path / "live-gaptv"
    work.mkdir()
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "reconstruct the cube",
                                 "--workdir", str(work)])
    assert result.exit_code == 0
    config = reg.load()
    agent = config.agents["work"]
    t = tsk.all_of(config, agent)[0]
    assert tsk.evidence_root(agent, t) == work.resolve()


def test_cli_do_refuses_a_working_directory_that_is_not_there(isolated, tmp_path):
    """Declaring a folder that does not exist would make every verdict
    UNVERIFIED later, for a reason stated nowhere near the mistake."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "x",
                                 "--workdir", str(tmp_path / "nope")])
    assert result.exit_code != 0
    assert "nope" in result.output


def test_cli_spend_reports_per_agent(isolated):
    _one_task("tidy the report folder")
    result = runner.invoke(app, ["sarsi", "spend"])
    assert result.exit_code == 0
    assert "work" in result.output


def test_cli_spend_never_prints_zero_pwm(isolated):
    """'0 PWM' reads as free; these sessions are simply not metered here."""
    _one_task()
    result = runner.invoke(app, ["sarsi", "spend"])
    assert "0 PWM" not in result.output
    assert "not charged" in result.output.lower()


def test_cli_spend_for_one_task(isolated):
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "spend", "--agent", "work",
                                 "--task", t.id])
    assert result.exit_code == 0
    assert t.id in result.output


def test_cli_spend_says_not_recorded_rather_than_zero_tokens(isolated):
    """A task with no transcript must not report 0 tokens."""
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "spend", "--agent", "work",
                                 "--task", t.id])
    assert "not started" in result.output.lower() or "not recorded" in result.output.lower()


def test_cli_decisions_lists_what_the_agent_did_alone(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "reports",
                  {"agent": "work", "task": "tsk_1", "state": "answered",
                   "ceiling": "A2", "evidence": ["the folder-trust prompt"]})
    result = runner.invoke(app, ["sarsi", "decisions"])
    assert result.exit_code == 0
    assert "A2" in result.output and "folder-trust" in result.output


def test_cli_decisions_is_quiet_when_the_agent_decided_nothing(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "decisions"])
    assert "nothing decided without you" in result.output.lower()


def test_cli_decisions_ack_moves_the_line(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "reports",
                  {"agent": "work", "task": "tsk_1", "state": "answered",
                   "ceiling": "A2", "evidence": ["x"]})
    runner.invoke(app, ["sarsi", "decisions", "--agent", "work", "--ack"])
    result = runner.invoke(app, ["sarsi", "decisions", "--agent", "work"])
    assert "nothing decided without you" in result.output.lower()


def test_cli_decisions_ack_needs_an_agent(isolated):
    """Acknowledging the whole fleet in one keystroke is how a real one gets
    skimmed past."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "decisions", "--ack"])
    assert result.exit_code != 0


def test_cli_blast_reports_the_declared_paths(isolated):
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "blast", "work", t.id])
    assert result.exit_code == 0
    assert "declared" in result.output.lower()


def test_cli_blast_does_not_claim_clean_without_a_record(isolated):
    """No transcript is not a clean bill."""
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "blast", "work", t.id])
    assert "clean" not in result.output.lower() or "not a clean" in result.output.lower()


def test_cli_questions_lists_open_escalations(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "reports",
                  {"agent": "work", "task": "tsk_1", "state": "question",
                   "evidence": ["Q: which directory should I index?",
                                "escalated: the plan does not settle it"]})
    result = runner.invoke(app, ["sarsi", "questions"])
    assert result.exit_code != 0            # something waits on you
    assert "which directory should I index?" in result.output


def test_cli_questions_is_quiet_when_none_are_open(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "questions"])
    assert result.exit_code == 0
    assert "no open questions" in result.output.lower()


def test_cli_answer_refuses_when_the_answer_would_reach_nobody(isolated):
    from ai4science.harness.agents.sarsi import ledger, task as tsk
    config, agent, t = _one_task()
    ledger.append(config, "reports",
                  {"agent": "work", "task": t.id, "state": "question",
                   "evidence": ["Q: which directory?", "escalated: x"]})
    result = runner.invoke(app, ["sarsi", "answer", "work", t.id,
                                 "which directory?", "/srv/exports"])
    assert result.exit_code != 0
    assert "no session" in result.output.lower()


def test_cli_attention_reports_a_terminal_no_task_claims(isolated, monkeypatch):
    """The CLI must actually ASK tmux, or the check never engages."""
    from ai4science.harness.agents.sarsi import entry
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    monkeypatch.setattr(entry, "_live_names", lambda: {"work-9zz9"})
    result = runner.invoke(app, ["sarsi", "attention"])
    assert "work-9zz9" in result.output
    assert result.exit_code == 1


def test_cli_undo_names_the_last_act_and_refuses_to_recall_mail(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "outward",
                  {"agent": "work", "task": "tsk_1", "kind": "mail",
                   "destination": "them@example.com", "digest": "abc123",
                   "chars": 120, "outcome": "sent"})
    result = runner.invoke(app, ["sarsi", "undo", "work"])
    assert result.exit_code != 0
    assert "them@example.com" in result.output
    assert "recall" in result.output.lower()


def test_cli_undo_with_nothing_outstanding_says_so(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "undo", "work"])
    assert "nothing" in result.output.lower()


def test_cli_undo_shows_without_acting_when_asked(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "outward",
                  {"agent": "work", "task": "tsk_1", "kind": "post",
                   "destination": "mastodon", "digest": "d1", "chars": 40,
                   "outcome": "posted"})
    result = runner.invoke(app, ["sarsi", "undo", "work", "--show"])
    assert result.exit_code == 0
    assert "mastodon" in result.output
    assert len(ledger.read(config, "outward")) == 1      # nothing attempted


def test_cli_undo_wires_a_retractor_for_a_known_platform(isolated, monkeypatch):
    """Without this the CLI can identify the post and still have nothing to
    call, which is the gap `undo` shipped with."""
    from ai4science.harness.agents.sarsi import ledger, transmit
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "outward",
                  {"agent": "social", "task": "tsk_1", "kind": "post",
                   "destination": "x", "digest": "d1", "chars": 12,
                   "outcome": "sent", "handle": "110045"})
    seen = []
    monkeypatch.setattr(transmit, "retractor",
                        lambda *a, **k: (lambda act: seen.append(act.handle)))
    result = runner.invoke(app, ["sarsi", "undo", "social"])
    assert result.exit_code == 0
    assert seen == ["110045"]


def test_cli_undo_on_an_unknown_platform_refuses_clearly(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "outward",
                  {"agent": "social", "task": "tsk_1", "kind": "post",
                   "destination": "carrier-pigeon", "digest": "d1", "chars": 12,
                   "outcome": "sent", "handle": "110045"})
    result = runner.invoke(app, ["sarsi", "undo", "social"])
    assert result.exit_code != 0
    assert "carrier-pigeon" in result.output


def test_cli_do_can_declare_a_budget(isolated, tmp_path):
    from ai4science.harness.agents.sarsi import task as tsk
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "index the exports",
                                 "--steps", "40", "--minutes", "30"])
    assert result.exit_code == 0
    config = reg.load()
    t = tsk.all_of(config, config.agents["work"])[0]
    assert (t.max_steps, t.max_minutes) == (40, 30)


def test_cli_do_says_what_the_budget_is(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "x", "--minutes", "30"])
    assert "30" in result.output and "minute" in result.output.lower()


def test_cli_do_refuses_a_budget_of_zero(isolated):
    """A budget of zero stops the task before it starts, which is not a budget
    — it is a way to file work that can never run."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "work", "x", "--steps", "0"])
    assert result.exit_code != 0


def test_cli_handoff_writes_and_shows_it(isolated):
    _config, _agent, t = _one_task("tidy the report folder")
    result = runner.invoke(app, ["sarsi", "handoff", "work", t.id])
    assert result.exit_code == 0
    assert "tidy the report folder" in result.output
    assert "HANDOFF.md" in result.output


def test_cli_do_can_declare_a_dependency(isolated):
    from ai4science.harness.agents.sarsi import task as tsk
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "do", "work", "produce the numbers"])
    config = reg.load()
    first = tsk.all_of(config, config.agents["work"])[0]
    result = runner.invoke(app, ["sarsi", "do", "funding", "use the numbers",
                                 "--after", f"work/{first.id}"])
    assert result.exit_code == 0
    assert first.id in result.output
    second = tsk.all_of(reg.load(), reg.load().agents["funding"])[0]
    assert second.state != tsk.RUNNING


def test_cli_do_refuses_a_dependency_that_does_not_exist(isolated):
    """A task waiting forever on nothing must say so while you are looking."""
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "do", "funding", "x",
                                 "--after", "work/tsk_nothing"])
    assert result.exit_code != 0
    assert "tsk_nothing" in result.output


def test_cli_rules_adds_and_lists(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "rules", "work", "--add",
                        "use python3 on this host, never python"])
    result = runner.invoke(app, ["sarsi", "rules", "work"])
    assert result.exit_code == 0
    assert "use python3 on this host" in result.output


def test_cli_rules_refuses_a_secret_value(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "rules", "work", "--add",
                                 "the smtp password is hunter2"])
    assert result.exit_code != 0
    assert "vault" in result.output.lower()


def test_cli_rules_can_remove_one(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "rules", "work", "--add", "use python3"])
    runner.invoke(app, ["sarsi", "rules", "work", "--remove", "use python3"])
    result = runner.invoke(app, ["sarsi", "rules", "work"])
    assert "no house rules" in result.output.lower()


def test_cli_digest_reports_across_the_fleet(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "reports",
                  {"agent": "social", "task": "tsk_1", "state": "verified",
                   "ceiling": "A2", "evidence": ["done"]})
    result = runner.invoke(app, ["sarsi", "digest"])
    assert result.exit_code == 0
    assert "social" in result.output and "1 verified" in result.output


def test_cli_digest_reading_does_not_consume_it(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "reports",
                  {"agent": "social", "task": "tsk_1", "state": "verified",
                   "ceiling": "A2", "evidence": ["done"]})
    runner.invoke(app, ["sarsi", "digest"])
    result = runner.invoke(app, ["sarsi", "digest"])
    assert "1 verified" in result.output


def test_cli_digest_deliver_moves_the_line(isolated):
    from ai4science.harness.agents.sarsi import ledger
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    config = reg.load()
    ledger.append(config, "reports",
                  {"agent": "social", "task": "tsk_1", "state": "verified",
                   "ceiling": "A2", "evidence": ["done"]})
    runner.invoke(app, ["sarsi", "digest", "--agent", "social", "--deliver"])
    result = runner.invoke(app, ["sarsi", "digest", "--agent", "social"])
    assert "nothing happened" in result.output.lower()


def test_cli_who_suggests_a_worker(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "who", "run the qupath segmentation"])
    assert result.exit_code == 0
    assert "work" in result.output and "qupath" in result.output


def test_cli_who_creates_nothing(isolated):
    from ai4science.harness.agents.sarsi import task as tsk
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    runner.invoke(app, ["sarsi", "who", "post the thread"])
    config = reg.load()
    assert all(not tsk.all_of(config, a) for a in config.agents.values())


def test_cli_who_declines_to_guess(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "who", "handle the thing"])
    assert "cannot tell" in result.output.lower()


def test_cli_handoff_proposes_and_accepts(isolated):
    from ai4science.harness.agents.sarsi import task as tsk, verifier as vf
    config, agent, t = _one_task("produce the benchmark numbers")
    tsk.finish(config, agent, t, verdict=vf.parse("PASS: 1,204 rows"))

    proposed = runner.invoke(app, ["sarsi", "handoff", "work", t.id,
                                   "--to", "funding",
                                   "--goal", "draft the application",
                                   "--because", "the numbers are verified"])
    assert proposed.exit_code == 0
    shown = runner.invoke(app, ["sarsi", "handoff", "funding"])
    assert "draft the application" in shown.output

    runner.invoke(app, ["sarsi", "handoff", "funding", "--accept"])
    config = reg.load()
    goals = [x.goal for x in tsk.all_of(config, config.agents["funding"])]
    assert goals == ["draft the application"]


def test_cli_handoff_refuses_unfinished_work(isolated):
    _config, _agent, t = _one_task()
    result = runner.invoke(app, ["sarsi", "handoff", "work", t.id,
                                 "--to", "funding", "--goal", "draft it",
                                 "--because", "x"])
    assert result.exit_code != 0
    assert "claim" in result.output.lower() or "pass" in result.output.lower()


def test_cli_board_writes_a_page_without_serving(isolated, tmp_path):
    """So it can be opened from a file, with no listener at all."""
    _one_task("tidy the report folder")
    out = tmp_path / "board.html"
    result = runner.invoke(app, ["sarsi", "board", "work", "--write", str(out)])
    assert result.exit_code == 0
    assert "tidy the report folder" in out.read_text()


def test_cli_board_written_without_an_agent_is_the_index(isolated, tmp_path):
    _one_task()
    out = tmp_path / "index.html"
    runner.invoke(app, ["sarsi", "board", "--write", str(out)])
    text = out.read_text()
    assert "work" in text and "social" in text


def test_cli_board_refuses_a_non_local_host(isolated):
    runner.invoke(app, ["sarsi", "init", "--owner-id", "7007143162"])
    result = runner.invoke(app, ["sarsi", "board", "--host", "0.0.0.0"])
    assert result.exit_code != 0
    assert "network" in result.output.lower() or "local" in result.output.lower()

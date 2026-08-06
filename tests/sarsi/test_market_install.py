"""§11, the half that works with nothing else installed.

The market has two halves and the page's own governing property splits them:

    This page is about ai4science alone, on one machine. Everything here works
    with nothing else installed.

**Uploading, the governor's acceptance and the PWM earning need a server**, and
the doc assigns that to the app. What a single machine can have is the rest, and
it is the part that matters for safety: **the package format, and installing
one here** — because an agent is a thing you install on your own machine and run
with your own keys.

So the acceptance questions are asked at INSTALL, by the machine doing the
installing, not taken on trust from a listing:

  * **a package may not ship a workspace or a task list.** One arriving with
    tasks in it files work the owner never asked for, past `CAP`, past the plan,
    past the grant — the install is the consent step and pre-filled work walks
    straight through it. One arriving with a workspace is an author writing
    standing instructions into a place the agent reads at plan time.
  * **the four reserved classes are refused at any ceiling** — `money`,
    `consent`, `publishing`, `legal`. A package claiming one is refused, not
    silently stripped: an author who asked for it should be told no.
  * **an agent does not set its own ceiling.** That is the owner's, and a
    manifest that could set it would make installing an agent a way to grant
    one.
  * **trust is not transitive.** An agent may bring its own tools; the install
    names every author whose code comes with it and what each part may touch.

Adversarial first, because every one of these is a way a package could take
something the owner did not give it.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import market, registry as reg

GOOD = {
    "id": "protein-fold",
    "version": "1.2.0",
    "author": {"handle": "ada", "pwm_address": "0x" + "a" * 40},
    "purpose": "fold a protein and report the confidence",
    "tools": ["browser"],
    "outward": [],
    "reserved_refused": ["money", "consent", "publishing", "legal"],
    "price_share": 1.0,
    "requires": {"ai4science": ">=0.1"},
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "state"))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    """A registry ON DISK — installing edits the file, not a parsed copy."""
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    path = reg.config_path(root)
    path.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(path)
    c.ensure_dirs()
    return c


def _package(tmp_path, manifest=None, *, spec="What it is for.",
             roster=None, extra=()):
    d = tmp_path / "pkg"
    d.mkdir(exist_ok=True)
    (d / "agent.json").write_text(json.dumps(manifest or GOOD))
    (d / "spec.md").write_text(spec)
    (d / "roster.json").write_text(json.dumps(
        roster if roster is not None else {"tools": ["browser"], "outward": []}))
    for rel in extra:
        p = d / rel
        p.mkdir(parents=True, exist_ok=True)
        (p / "keep").write_text("x")
    return d


# ── a package may not ship what the installer creates ─────────────────

@pytest.mark.parametrize("shipped", ["workspace", "tasks"])
def test_a_package_shipping_state_is_refused(config, tmp_path, shipped):
    with pytest.raises(market.Refused, match=shipped):
        market.install(config, _package(tmp_path, extra=[shipped]))


def test_and_it_says_why_rather_than_stripping_it(config, tmp_path):
    """Silently removing it would install an author's intent and not mention
    it. The owner is told what the package tried to bring."""
    with pytest.raises(market.Refused) as e:
        market.install(config, _package(tmp_path, extra=["tasks"]))
    assert "installer" in str(e.value).lower() or "creates" in str(e.value).lower()


# ── the reserved classes ──────────────────────────────────────────────

@pytest.mark.parametrize("klass", ["money", "consent", "publishing", "legal"])
def test_a_package_claiming_a_reserved_class_is_refused(config, tmp_path, klass):
    bad = dict(GOOD, outward=[klass])
    with pytest.raises(market.Refused, match=klass):
        market.install(config, _package(tmp_path, bad))


def test_including_when_it_hides_in_the_roster(config, tmp_path):
    """Two files declare outward classes. Checking one is checking neither."""
    with pytest.raises(market.Refused, match="money"):
        market.install(config, _package(
            tmp_path, roster={"tools": ["browser"], "outward": ["money"]}))


# ── an agent does not grant itself anything ───────────────────────────

def test_a_manifest_cannot_set_its_own_ceiling(config, tmp_path):
    """Installing an agent would otherwise be a way to grant one."""
    with pytest.raises(market.Refused, match="ceiling"):
        market.install(config, _package(tmp_path, dict(GOOD, ceiling="A3")))


def test_nor_turn_off_the_things_that_watch_it(config, tmp_path):
    for field in ("standing_grants", "retired", "digest"):
        with pytest.raises(market.Refused, match=field):
            market.install(config, _package(tmp_path, dict(GOOD, **{field: True})))


# ── the id is a directory name, and is checked like one ───────────────

@pytest.mark.parametrize("bad_id", ["../../etc", "a/b", ".", "", "x" * 200,
                                    "with space", "Upper"])
def test_an_id_that_is_not_a_safe_name_is_refused(config, tmp_path, bad_id):
    with pytest.raises(market.Refused):
        market.install(config, _package(tmp_path, dict(GOOD, id=bad_id)))


def test_an_id_that_is_already_installed_is_refused(config, tmp_path):
    """Every directory and session store is keyed by id. A collision would
    hand a new author another agent's history."""
    with pytest.raises(market.Refused, match="sarsi-worker"):
        market.install(config, _package(tmp_path, dict(GOOD, id="sarsi-worker")))


# ── the manifest has to be readable at all ────────────────────────────

def test_a_package_with_no_manifest_is_refused(config, tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    with pytest.raises(market.Refused, match="agent.json"):
        market.install(config, d)


def test_an_unparseable_manifest_is_refused(config, tmp_path):
    d = _package(tmp_path)
    (d / "agent.json").write_text("{not json")
    with pytest.raises(market.Refused):
        market.install(config, d)


def test_a_version_this_ai4science_does_not_meet_is_refused(config, tmp_path):
    bad = dict(GOOD, requires={"ai4science": ">=99.0"})
    with pytest.raises(market.Refused, match="99"):
        market.install(config, _package(tmp_path, bad))


def test_a_price_share_outside_the_slice_is_refused(config, tmp_path):
    for share in (-0.1, 1.5):
        with pytest.raises(market.Refused, match="price_share"):
            market.install(config, _package(tmp_path, dict(GOOD,
                                                           price_share=share)))


# ── what it does when it accepts ──────────────────────────────────────

def test_an_accepted_package_joins_the_roster(config, tmp_path):
    market.install(config, _package(tmp_path))
    fresh = reg.load(config.path)
    assert "protein-fold" in fresh.agents
    assert fresh.agents["protein-fold"].tools == ["browser"]


def test_it_runs_at_the_everyday_ceiling_like_everything_else(config, tmp_path):
    market.install(config, _package(tmp_path))
    fresh = reg.load(config.path)
    assert fresh.agents["protein-fold"].ceiling == reg.EVERYDAY_CEILING


def test_it_gets_an_empty_workspace_and_task_list(config, tmp_path):
    market.install(config, _package(tmp_path))
    agent = reg.load(config.path).agents["protein-fold"]
    assert agent.workspace.is_dir() and not any(agent.workspace.iterdir())
    assert agent.tasks.is_dir() and not any(agent.tasks.iterdir())


def test_the_install_names_every_author_whose_code_comes_with_it(config, tmp_path):
    """Trust is not transitive. A package bringing a tool brings its author."""
    d = _package(tmp_path)
    (d / "tools").mkdir()
    (d / "tools" / "pymol.json").write_text(json.dumps(
        {"name": "pymol", "author": {"handle": "linus"}, "touches": ["gpu"]}))
    report = market.install(config, d)
    handles = {a["handle"] for a in report.authors}
    assert handles == {"ada", "linus"}
    assert any("gpu" in (a.get("touches") or []) for a in report.authors)


def test_and_says_what_it_installed(config, tmp_path):
    report = market.install(config, _package(tmp_path))
    assert report.agent_id == "protein-fold"
    assert "fold a protein" in report.purpose


# ── and it can be listed and removed ──────────────────────────────────

def test_an_installed_package_is_listed(config, tmp_path):
    market.install(config, _package(tmp_path))
    assert "protein-fold" in [p.agent_id for p in market.installed(config)]


def test_removing_it_takes_it_out_of_the_roster(config, tmp_path):
    market.install(config, _package(tmp_path))
    market.remove(config, "protein-fold")
    assert "protein-fold" not in reg.load(config.path).agents


def test_but_not_one_that_shipped_with_the_machine(config, tmp_path):
    """The seven are not market listings and removing one is not an uninstall."""
    with pytest.raises(market.Refused, match="shipped"):
        market.remove(config, "sarsi-worker")


def test_removing_keeps_its_history(config, tmp_path):
    """Same reasoning as retiring: a folder is the record of what it did."""
    market.install(config, _package(tmp_path))
    agent = reg.load(config.path).agents["protein-fold"]
    (agent.tasks / "tsk_x").mkdir(parents=True)
    market.remove(config, "protein-fold")
    assert (agent.tasks / "tsk_x").is_dir()


# ── and it is reachable from the CLI ──────────────────────────────────

def _cli():
    from typer.testing import CliRunner
    from ai4science.cli import app
    return CliRunner(), app


def test_install_from_the_cli(config, tmp_path):
    runner, app = _cli()
    res = runner.invoke(app, ["sarsi", "market", "install", str(_package(tmp_path))])
    assert res.exit_code == 0, res.output
    assert "protein-fold" in res.output


def test_the_install_shows_every_author_before_it_is_done(config, tmp_path):
    """Trust is not transitive, and the owner reads this line."""
    d = _package(tmp_path)
    (d / "tools").mkdir()
    (d / "tools" / "pymol.json").write_text(json.dumps(
        {"name": "pymol", "author": {"handle": "linus"}, "touches": ["gpu"]}))
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "market", "install", str(d)]).output
    assert "ada" in out and "linus" in out
    assert "gpu" in out


def test_a_refusal_reaches_the_owner_with_its_reason(config, tmp_path):
    runner, app = _cli()
    res = runner.invoke(app, ["sarsi", "market", "install",
                              str(_package(tmp_path, dict(GOOD, outward=["money"])))])
    assert res.exit_code != 0
    assert "money" in res.output


def test_listing_what_is_installed(config, tmp_path):
    runner, app = _cli()
    runner.invoke(app, ["sarsi", "market", "install", str(_package(tmp_path))])
    out = runner.invoke(app, ["sarsi", "market", "list"]).output
    assert "protein-fold" in out and "ada" in out


def test_an_empty_market_says_so_rather_than_printing_nothing(config):
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "market", "list"]).output
    assert "nothing" in out.lower() or "no " in out.lower()


def test_removing_from_the_cli(config, tmp_path):
    runner, app = _cli()
    runner.invoke(app, ["sarsi", "market", "install", str(_package(tmp_path))])
    res = runner.invoke(app, ["sarsi", "market", "remove", "protein-fold"])
    assert res.exit_code == 0
    assert "protein-fold" not in runner.invoke(
        app, ["sarsi", "market", "list"]).output


def test_and_it_says_the_history_stays(config, tmp_path):
    runner, app = _cli()
    runner.invoke(app, ["sarsi", "market", "install", str(_package(tmp_path))])
    out = runner.invoke(app, ["sarsi", "market", "remove", "protein-fold"]).output
    assert "history" in out.lower() or "kept" in out.lower()

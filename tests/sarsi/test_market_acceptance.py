"""Upload and acceptance — the trust half, which does not need the server.

The design says uploading and the governor's acceptance need somewhere to
upload *to*. That is true of the **transport** and false of the **trust**, and
keeping the two apart is the whole of this:

  * **`pack`** seals a directory into a listing with a content **digest**. What
    was reviewed and what gets installed are the same bytes or the install
    says so.
  * **`review`** runs the acceptance questions — mechanically, on this machine,
    by anyone. Acceptance stops being a claim the market makes and becomes a
    thing a reader can re-run and get the same answer.
  * **`accept`** is a **signature** over that digest. It is the governor's only
    contribution, because it is the only part that is judgement rather than
    arithmetic. Same propose/hold/sign shape as house rules and plan adoption.
  * **`install`** then says which it has: accepted by whom, or **unreviewed**.

Whether the listing travelled by HTTP, a shared directory or a USB stick does
not enter into it. That is why the server is a transport detail here and not
the thing being trusted.

**Review does not run the package's code, and that is deliberate.** `tests/` is
"what the author says proves it works" — running it to decide whether the
author can be trusted means executing untrusted code to find out whether it is
trustworthy. The review records that tests exist and what they claim; running
them is the installer's own call, on their own machine, after they have decided.
"""
import json
import shutil

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
    root = tmp_path / "state"
    root.mkdir(parents=True, exist_ok=True)
    path = reg.config_path(root)
    path.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(path)
    c.ensure_dirs()
    return c


def _package(tmp_path, manifest=None, *, name="pkg", tests=True):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    (d / "agent.json").write_text(json.dumps(manifest or GOOD))
    (d / "spec.md").write_text("What it is for.")
    (d / "roster.json").write_text(json.dumps({"tools": ["browser"],
                                               "outward": []}))
    if tests:
        (d / "tests").mkdir(exist_ok=True)
        (d / "tests" / "test_it.py").write_text("def test_ok():\n    assert 1\n")
    return d


# ── pack: what was reviewed is what gets installed ────────────────────

def test_packing_seals_the_contents(tmp_path):
    listing = market.pack(_package(tmp_path))
    assert listing.digest and len(listing.digest) >= 32
    assert listing.agent_id == "protein-fold"


def test_the_same_bytes_give_the_same_digest(tmp_path):
    a = market.pack(_package(tmp_path, name="a"))
    b = market.pack(_package(tmp_path, name="b"))
    assert a.digest == b.digest


def test_and_one_changed_byte_gives_another(tmp_path):
    d = _package(tmp_path)
    first = market.pack(d).digest
    (d / "spec.md").write_text("What it is for, actually.")
    assert market.pack(d).digest != first


def test_a_file_added_after_packing_changes_it_too(tmp_path):
    """The escape a digest over the manifest alone would leave open: ship the
    reviewed manifest and a tool nobody looked at."""
    d = _package(tmp_path)
    first = market.pack(d).digest
    (d / "tools").mkdir(exist_ok=True)
    (d / "tools" / "extra.json").write_text("{}")
    assert market.pack(d).digest != first


# ── review: the acceptance questions, run by anyone ───────────────────

def test_a_sound_package_reviews_clean(tmp_path):
    got = market.review(_package(tmp_path))
    assert got.ok is True, got.problems


@pytest.mark.parametrize("manifest,word", [
    (dict(GOOD, outward=["money"]), "money"),
    (dict(GOOD, ceiling="A3"), "ceiling"),
    (dict(GOOD, id="../../etc"), "id"),
    (dict(GOOD, price_share=9), "price_share"),
])
def test_review_asks_the_same_questions_the_install_does(tmp_path, manifest,
                                                         word):
    """One set of rules. A package that reviews clean and then refuses to
    install would make the review worth nothing."""
    got = market.review(_package(tmp_path, manifest))
    assert got.ok is False
    assert any(word in p for p in got.problems), got.problems


def test_review_says_what_the_author_claims_proves_it(tmp_path):
    got = market.review(_package(tmp_path))
    assert got.tests == ["tests/test_it.py"]


def test_and_a_package_with_no_tests_is_not_refused_for_it(tmp_path):
    """The author claiming nothing is a fact about the listing, not a defect
    in it — the owner reads it and decides."""
    got = market.review(_package(tmp_path, tests=False))
    assert got.ok is True
    assert got.tests == []


def test_review_does_not_execute_the_package(tmp_path):
    """Running `tests/` to decide whether the author can be trusted means
    executing untrusted code to find out whether it is trustworthy."""
    d = _package(tmp_path)
    (d / "tests" / "test_it.py").write_text(
        "import pathlib\n"
        "pathlib.Path('/tmp/sarsi-review-ran').write_text('x')\n")
    import pathlib
    pathlib.Path("/tmp/sarsi-review-ran").unlink(missing_ok=True)
    market.review(d)
    assert not pathlib.Path("/tmp/sarsi-review-ran").exists()


# ── accept: a signature over that digest, and nothing else ────────────

def test_an_acceptance_is_over_the_digest(tmp_path):
    listing = market.pack(_package(tmp_path))
    acc = market.accept(listing, by="governor", key="k")
    assert acc.digest == listing.digest
    assert acc.by == "governor"


def test_an_acceptance_does_not_travel_to_another_package(tmp_path):
    """The bait-and-switch: review one thing, ship another."""
    good = market.pack(_package(tmp_path, name="a"))
    acc = market.accept(good, by="governor", key="k")
    other = _package(tmp_path, dict(GOOD, tools=["browser", "shell"]),
                     name="b")
    assert market.acceptance_of(other, [acc]) is None


def test_nor_survive_the_package_being_edited_after_it(tmp_path):
    d = _package(tmp_path)
    acc = market.accept(market.pack(d), by="governor", key="k")
    assert market.acceptance_of(d, [acc]) is not None
    (d / "agent.json").write_text(json.dumps(dict(GOOD, tools=["shell"])))
    assert market.acceptance_of(d, [acc]) is None


def test_a_forged_signature_is_not_an_acceptance(tmp_path):
    d = _package(tmp_path)
    acc = market.accept(market.pack(d), by="governor", key="k")
    acc.signature = "0" * len(acc.signature)
    assert market.acceptance_of(d, [acc]) is None


def test_a_package_that_would_not_review_cannot_be_accepted(tmp_path):
    """Signing is judgement ON TOP of the checks, not instead of them."""
    bad = _package(tmp_path, dict(GOOD, outward=["money"]))
    with pytest.raises(market.Refused, match="money"):
        market.accept(market.pack(bad), by="governor", key="k")


# ── install says which it has ─────────────────────────────────────────

def test_an_unreviewed_package_installs_and_says_so(config, tmp_path):
    """The owner's machine and the owner's call — but never quietly."""
    report = market.install(config, _package(tmp_path))
    assert report.accepted_by == []
    assert "unreviewed" in report.standing.lower()


def test_an_accepted_one_names_who_accepted_it(config, tmp_path):
    d = _package(tmp_path)
    acc = market.accept(market.pack(d), by="governor", key="k")
    report = market.install(config, d, acceptances=[acc])
    assert report.accepted_by == ["governor"]
    assert "unreviewed" not in report.standing.lower()


def test_an_acceptance_for_something_else_leaves_it_unreviewed(config, tmp_path):
    other = market.accept(market.pack(_package(tmp_path, name="a")),
                          by="governor", key="k")
    report = market.install(config, _package(tmp_path, dict(GOOD, tools=[]),
                                             name="b"),
                            acceptances=[other])
    assert report.accepted_by == []


def test_acceptance_does_not_get_a_package_past_the_refusals(config, tmp_path):
    """A signature is not a waiver. The install asks its own questions of every
    package, whoever signed it — that is what makes a sideloaded package and an
    accepted one equally safe to install."""
    bad = _package(tmp_path, dict(GOOD, outward=["publishing"]))
    forged = market.Acceptance(digest=market.pack(bad).digest, by="governor",
                               signature="x", at="now")
    with pytest.raises(market.Refused, match="publishing"):
        market.install(config, bad, acceptances=[forged])


# ── the transport is a detail, and is one ─────────────────────────────

def _cli():
    from typer.testing import CliRunner
    from ai4science.cli import app
    return CliRunner(), app


def test_publish_puts_a_listing_where_a_governor_can_read_it(config, tmp_path):
    """`upload` with no server: the same file-inbox handshake the compute
    design already uses. HTTP later is a change of transport, not of trust."""
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "market", "publish",
                              str(_package(tmp_path))]).output
    box = config.root / "market" / "outbox"
    listings = list(box.glob("*.json"))
    assert listings, out
    body = json.loads(listings[0].read_text())
    assert body["agent_id"] == "protein-fold" and body["digest"]


def test_review_from_the_cli_names_every_problem_at_once(config, tmp_path):
    """An author fixing four things should be told four things."""
    runner, app = _cli()
    bad = _package(tmp_path, dict(GOOD, outward=["money"], ceiling="A3"))
    res = runner.invoke(app, ["sarsi", "market", "review", str(bad)])
    assert res.exit_code != 0
    assert "ceiling" in res.output


def test_a_clean_review_says_what_the_author_claims(config, tmp_path):
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "market", "review",
                              str(_package(tmp_path))]).output
    assert "test_it.py" in out
    assert "not run" in out.lower() or "did not run" in out.lower()


def test_install_tells_the_owner_it_is_unreviewed(config, tmp_path):
    runner, app = _cli()
    out = runner.invoke(app, ["sarsi", "market", "install",
                              str(_package(tmp_path))]).output
    assert "unreviewed" in out.lower()

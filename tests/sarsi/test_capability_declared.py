"""Telling `CAP` about a tool it has no probe for.

The design carried a note saying `CAP` falls back to `shutil.which` for anything
not named in `tools.json`, so `shell`, `editor` and `browser` were decided by
whatever unrelated binaries happened to be installed. **That is not what this
code does**, and I merged the note into the design yesterday on a shallow check
— I grepped, saw `tools.json` and `shutil.which` in the file, and treated the
symbols existing as confirming the behaviour. Run against the real registry, all
seven agents answer honestly and specifically:

    shell     True   always present on this machine
    browser   False  not on PATH (chromium, chromium-browser, google-chrome, firefox)
    mail      False  not configured — no account for it yet
    matlab    False  not on PATH (matlab)

`_INHERENT`, `_NEEDS_CONFIG` and the candidate lists already do the job, and a
tool with no probe is reported absent *with its reason* rather than guessed at.

The real gap is one layer down, and it is what the note was reaching for.
`tools.json` is a probe CACHE: an absent entry is re-probed every time and a
present one ages out in fifteen minutes. So there is **no way for the owner to
tell `CAP` about a tool it has no probe for** — `zotero`, an in-house CLI, a
GUI app that is not on `PATH`. Those are permanently absent, and `NOM` refuses
the work that needs them, with no way to say "it is here".

So a declaration is a different thing from a probe, and is kept apart from one:

  * **it does not age out.** A probe expires because software gets uninstalled;
    a declaration is the owner's standing word, and expiring it would mean
    re-declaring every fifteen minutes.
  * **it says it is a declaration.** `CAP`'s rule is *do not assume*, and the
    owner assuming responsibility is legitimate — but it is not evidence, and
    the report must not present it as though somebody looked.
  * **it never overrides a probe.** Where `CAP` can check, checking wins:
    declaring `matlab` present on a machine without `matlab` is a claim the
    probe can falsify, and a system that let a declaration win there would let
    an owner turn off the one check that catches this.
"""
import pytest

from ai4science.harness.agents.sarsi import capability as cap, registry as reg


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def config(tmp_path):
    c = reg.parse(reg.default_config(owner_id="7007143162"), root=tmp_path)
    c.ensure_dirs()
    return c


@pytest.fixture
def agent(config):
    return config.agents["work"]


def _none(_name):
    return None                       # nothing on PATH


# ── what the note was reaching for ────────────────────────────────────

def test_a_tool_with_no_probe_can_be_declared(config, agent):
    """`zotero` is not a binary this knows, not inherent, not an account. Before
    this there was no way to say it is here."""
    cap.declare(config, agent, "zotero")
    got = cap.inventory(config, agent, ["zotero"], which=_none)
    assert got["zotero"].present is True


def test_the_report_says_it_was_declared_not_probed(config, agent):
    """The owner's word is legitimate and is not evidence. A report that read
    like somebody looked would be the assumption `CAP` exists to refuse."""
    cap.declare(config, agent, "zotero")
    how = cap.inventory(config, agent, ["zotero"], which=_none)["zotero"].how
    assert "declar" in how.lower()
    assert "owner" in how.lower()


def test_an_undeclared_unknown_tool_is_still_absent(config, agent):
    got = cap.inventory(config, agent, ["zotero"], which=_none)
    assert got["zotero"].present is False
    assert "no probe" in got["zotero"].how


def test_a_declaration_can_carry_the_owner_s_note(config, agent):
    cap.declare(config, agent, "zotero", note="the flatpak build")
    assert "flatpak" in cap.inventory(config, agent, ["zotero"],
                                      which=_none)["zotero"].how


# ── it is not a probe, and does not behave like one ───────────────────

def test_a_declaration_does_not_age_out(config, agent):
    """A probe expires because software gets uninstalled. A standing word that
    expired would have to be repeated every fifteen minutes."""
    cap.declare(config, agent, "zotero")
    got = cap.inventory(config, agent, ["zotero"], which=_none,
                        now=lambda: 10 ** 9, max_age=1.0)
    assert got["zotero"].present is True


def test_it_survives_the_cache_being_thrown_away(config, agent):
    """`tools.json` is a cache and is rewritten constantly; a declaration kept
    inside it would be one `_save` away from gone."""
    cap.declare(config, agent, "zotero")
    (agent.host / cap.INVENTORY_NAME).unlink(missing_ok=True)
    assert cap.inventory(config, agent, ["zotero"], which=_none)["zotero"].present


def test_it_can_be_withdrawn(config, agent):
    cap.declare(config, agent, "zotero")
    cap.undeclare(config, agent, "zotero")
    assert cap.inventory(config, agent, ["zotero"],
                         which=_none)["zotero"].present is False


# ── and it never overrides what can be checked ────────────────────────

def test_a_declaration_does_not_beat_a_probe(config, agent):
    """Declaring `matlab` present on a machine without it is a claim the probe
    can falsify. Letting the declaration win would switch off the one check
    that catches it."""
    cap.declare(config, agent, "matlab")
    got = cap.inventory(config, agent, ["matlab"], which=_none)
    assert got["matlab"].present is False
    assert "not on PATH" in got["matlab"].how


def test_nor_an_inherent_one(config, agent):
    cap.declare(config, agent, "shell")
    assert "always present" in cap.inventory(config, agent, ["shell"],
                                             which=_none)["shell"].how


def test_nor_an_account_this_machine_does_not_have(config, agent):
    """`mail` is absent because there is no account, and an owner cannot
    declare an account into existence."""
    cap.declare(config, agent, "mail")
    got = cap.inventory(config, agent, ["mail"], which=_none)
    assert got["mail"].present is False
    assert "not configured" in got["mail"].how


def test_declarations_are_per_agent(config):
    """A tool inventory is about a host AND about what this agent may use;
    `work` declaring something must not hand it to `abraham`."""
    work, abraham = config.agents["work"], config.agents["abraham"]
    cap.declare(config, work, "zotero")
    assert cap.inventory(config, abraham, ["zotero"],
                         which=_none)["zotero"].present is False


# ── what `NOM` then says ──────────────────────────────────────────────

def test_a_declared_tool_stops_being_reported_missing(config, agent):
    """The point of the whole thing: `missing` is what refuses the work."""
    assert cap.missing(config, agent, ["zotero"], which=_none) == ["zotero"]
    cap.declare(config, agent, "zotero")
    assert cap.missing(config, agent, ["zotero"], which=_none) == []


def test_a_declared_tool_is_visible_without_being_on_the_roster(config, agent):
    """Caught live. `inventory` with no list asks about the agent's ROSTER
    tools, so a freshly declared `zotero` was accepted, stored, honoured by
    `missing` — and absent from the listing the owner was looking at. A
    declaration you cannot see is one you cannot check or withdraw."""
    cap.declare(config, agent, "zotero")
    got = cap.inventory(config, agent, which=_none)
    assert "zotero" in got and got["zotero"].present is True

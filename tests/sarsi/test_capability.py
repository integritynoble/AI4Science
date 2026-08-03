"""`CAP` — is the tool actually here?

The rule this module exists to keep: **it may not assume.** Capability is a
property of *this* machine, probed for real, and an unknown tool is absent
rather than optimistically present. What it learns lives in `W_host` and stays
there — a tool inventory is about a host and means nothing off it.
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


def _which(present):
    """A fake PATH lookup: only the named binaries exist."""
    return lambda name: f"/usr/bin/{name}" if name in present else None


# ── probing ───────────────────────────────────────────────────────────

def test_a_binary_on_the_path_is_present_and_says_where(config):
    p = cap.probe("matlab", which=_which({"matlab"}))
    assert p.present is True and p.how == "/usr/bin/matlab"


def test_a_binary_not_on_the_path_is_absent(config):
    p = cap.probe("matlab", which=_which(set()))
    assert p.present is False


def test_an_unknown_tool_is_absent_never_assumed(config):
    """A tool nobody wrote a probe for cannot be reported as working."""
    p = cap.probe("time-machine", which=_which({"time-machine"}))
    assert p.present is False
    assert "no probe" in (p.how or "")


def test_a_tool_with_alternatives_is_present_if_any_one_is(config):
    """A browser is a browser whichever one is installed."""
    assert cap.probe("browser", which=_which({"chromium"})).present is True
    assert cap.probe("browser", which=_which({"firefox"})).present is True
    assert cap.probe("browser", which=_which(set())).present is False


def test_the_shell_is_always_here(config):
    assert cap.probe("shell", which=_which(set())).present is True


def test_a_tool_that_needs_configuration_is_absent_until_it_has_it(config):
    """`mail` is not a binary. Reporting it present because a mail client
    exists would be a claim about the account, which nobody has checked."""
    p = cap.probe("mail", which=_which({"thunderbird"}))
    assert p.present is False
    assert "configur" in (p.how or "").lower()


# ── the inventory in W_host ───────────────────────────────────────────

def test_inventory_is_written_to_this_agents_host_dir(config):
    agent = config.agents["work"]
    cap.inventory(config, agent, which=_which({"matlab"}))
    assert (agent.host / "tools.json").exists()


def test_inventory_covers_the_tools_the_agent_declares(config):
    agent = config.agents["work"]                     # qupath, matlab, mail
    inv = cap.inventory(config, agent, which=_which({"matlab"}))
    assert set(inv) == {"qupath", "matlab", "mail"}
    assert inv["matlab"].present is True and inv["qupath"].present is False


def test_a_fresh_hit_is_reused_rather_than_reprobed(config):
    agent = config.agents["work"]
    cap.inventory(config, agent, ["matlab"], which=_which({"matlab"}), now=lambda: 1000.0)
    calls = []

    def counting_which(name):
        calls.append(name)
        return None

    cap.inventory(config, agent, ["matlab"], which=counting_which, now=lambda: 1060.0)
    assert calls == []                                # a present tool, inside the max age


def test_a_cached_miss_is_reprobed_at_once(config):
    """Asymmetric on purpose. Being stale about a tool being *present* costs
    nothing — you find out when you use it. Being stale about a tool being
    *absent* blocks work that could run: the owner installs MATLAB because the
    agent said it was missing, asks again, and is told the same thing."""
    agent = config.agents["work"]
    cap.inventory(config, agent, ["matlab"], which=_which(set()), now=lambda: 1000.0)
    inv = cap.inventory(config, agent, ["matlab"], which=_which({"matlab"}),
                        now=lambda: 1001.0)
    assert inv["matlab"].present is True


def test_a_stale_inventory_is_reprobed_rather_than_trusted(config):
    agent = config.agents["work"]
    cap.inventory(config, agent, which=_which({"matlab"}), now=lambda: 1000.0)
    inv = cap.inventory(config, agent, which=_which(set()),
                        now=lambda: 1000.0 + cap.MAX_AGE_S + 1)
    assert inv["matlab"].present is False             # it was uninstalled; say so


def test_one_agents_inventory_is_not_anothers(config):
    """W_host is per agent; nothing here is promoted upward."""
    cap.inventory(config, config.agents["work"], which=_which({"matlab"}))
    assert not (config.agents["abraham"].host / "tools.json").exists()


# ── what the worker asks it ───────────────────────────────────────────

def test_missing_names_exactly_what_is_absent(config):
    agent = config.agents["work"]
    assert cap.missing(config, agent, ["matlab", "qupath"],
                       which=_which({"matlab"})) == ["qupath"]


def test_missing_is_empty_when_everything_is_here(config):
    agent = config.agents["work"]
    assert cap.missing(config, agent, ["matlab"], which=_which({"matlab"})) == []


def test_requiring_a_tool_the_agent_never_declared_is_still_probed(config):
    """A directive may ask for something outside the agent's usual kit; the
    honest answer is whether the machine has it, not whether the roster does."""
    agent = config.agents["abraham"]
    assert cap.missing(config, agent, ["matlab"], which=_which({"matlab"})) == []

"""`sarsi-pwm` renamed to `sarsi-ai4sci` — WITHOUT breaking what was written down.

The owner renamed the backend. A rename of a name that has been RECORDED is two
obligations, and only the first is a rename:

  * every task filed before today has `backend: "sarsi-pwm"` sitting in its
    `task.json`. Those files are not rewritten — `backends.py` says the backend
    is "a fact about the task — recorded with it, and not rewritten when a later
    task chooses differently". So the old spelling has to keep RESOLVING,
    forever. A record that stops reading is a task that stops running.
  * everything filed from now on records the NEW name, on disk, so the corpus
    converges instead of splitting in two.

The tests are in that order. The last two are the guards that make the rest mean
something: an alias must not become a blanket accept-anything, and `NAMES` must
stay a two-element toggle or the confirmation block's `b=` offer breaks.
"""
import json

import pytest

from ai4science.harness.agents.sarsi import (backends, registry as reg,
                                             task as tsk, worker as wk)

OLD = "sarsi-pwm"
NEW = "sarsi-ai4sci"


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("SARSI_STATE_DIR", str(tmp_path / "s"))
    root = tmp_path / "s"
    root.mkdir(parents=True, exist_ok=True)
    p = reg.config_path(root)
    p.write_text(json.dumps(reg.default_config(owner_id="7007143162")))
    c = reg.load(p)
    c.ensure_dirs()
    return c


# -- 1. the old name still reads -------------------------------------------

def test_a_task_recorded_as_the_old_name_still_reads(config):
    """A record persisted as `sarsi-pwm` keeps working after the rename.

    The literal string is put on disk deliberately rather than through
    `create(backend=OLD)`: once the alias exists `create` normalises it, and
    this test is about the bytes ALREADY in the file -- the ones nothing will
    ever rewrite.
    """
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))

    path = tsk.dir_of(a, t.id) / tsk.RECORD_NAME
    record = json.loads(path.read_text())
    record["backend"] = OLD                       # as it was written in 2026-08
    path.write_text(json.dumps(record, indent=2, sort_keys=True))

    loaded = tsk.get(config, a, t.id)
    assert loaded is not None
    assert loaded.backend == OLD, "the stored record must not be rewritten"

    # ...and every reader answers about it.
    assert backends.spec_for(OLD) == "ai4sci"
    assert backends.canonical(OLD) == NEW
    assert backends.resolve(OLD) == NEW
    assert "not a known backend" not in backends.describe(OLD)


def test_the_old_name_never_leaks_back_into_a_record(config):
    """Accepting the old spelling must not WRITE the old spelling."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"), backend=OLD)

    path = tsk.dir_of(a, t.id) / tsk.RECORD_NAME
    assert json.loads(path.read_text())["backend"] == NEW


def test_switching_by_the_old_name_records_the_new_one(config):
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"),
                   backend="sarsi-claude")
    said = tsk.set_backend(config, a, t, OLD)

    path = tsk.dir_of(a, t.id) / tsk.RECORD_NAME
    assert json.loads(path.read_text())["backend"] == NEW
    assert NEW in said and OLD not in said, said


# -- 2. the new name is what gets written -----------------------------------

def test_a_new_task_records_the_new_name(config):
    """Read back off disk: the in-memory object is not what the next process
    sees."""
    a = config.agents["sarsi-worker"]
    t = tsk.create(config, a, wk.Directive(agent_id=a.id, goal="g"))

    path = tsk.dir_of(a, t.id) / tsk.RECORD_NAME
    assert json.loads(path.read_text())["backend"] == NEW


def test_the_default_is_the_renamed_backend():
    assert backends.DEFAULT == NEW
    assert backends.resolve("") == NEW
    assert backends.spec_for(backends.DEFAULT) == "ai4sci"


# -- 3. the guards ----------------------------------------------------------

def test_an_unknown_name_is_still_refused_and_says_the_real_ones():
    """THE DELIBERATELY FAILING CASE, written as a passing assertion about a
    refusal. An alias is a hole in a whitelist; a near-miss typo of the OLD
    name must go through the hole and be REFUSED, or the alias has quietly
    become accept-anything and every wrong name picks an engine nobody chose.
    """
    with pytest.raises(backends.NoSuchBackend) as e:
        backends.spec_for("sarsi-pw")
    assert NEW in str(e.value) and "sarsi-claude" in str(e.value)
    # and the offer names what exists NOW, not the alias
    assert OLD not in str(e.value), "the error must not advertise the old name"
    assert "not a known backend" in backends.describe("sarsi-pw")


def test_names_is_the_two_real_backends_and_not_the_alias():
    """`console.confirm_block` picks the OTHER backend with
    `next(n for n in NAMES if n != chosen)`. A three-element NAMES turns the
    owner's `b` toggle into a wrong answer, silently."""
    assert set(backends.NAMES) == {"sarsi-claude", NEW}
    assert OLD not in backends.NAMES


def test_the_alias_is_declared_rather_than_guessed():
    assert backends.ALIASES.get(OLD) == NEW
    assert backends.canonical("sarsi-claude") == "sarsi-claude"
    assert backends.canonical("  sarsi-pwm  ") == NEW


# -- 4. room for the next motor --------------------------------------------

def test_the_b_offer_cycles_rather_than_assuming_there_are_two():
    """`console.confirm_block` used `next(n for n in NAMES if n != chosen)`.
    That is correct for two backends and silently WRONG for three: `b` would
    return the first non-matching name every time, so one engine could never
    be reached from the confirmation at all. A third motor is coming; this is
    the trap taken out before somebody steps in it."""
    assert backends.next_after("sarsi-claude") == NEW
    assert backends.next_after(NEW) == "sarsi-claude"
    assert backends.next_after(OLD) == "sarsi-claude", "the alias cycles too"
    assert backends.next_after("") == backends.next_after(backends.DEFAULT)

    # and it really cycles: pressing b once per backend comes home.
    seen, at = [], backends.DEFAULT
    for _ in backends.NAMES:
        at = backends.next_after(at)
        seen.append(at)
    assert set(seen) == set(backends.NAMES), seen
    assert at == backends.DEFAULT, "a full cycle must return to where it began"

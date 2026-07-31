import pytest

from ai4science.harness.agents.machine import supervisor as sup


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_CP_STATE_DIR", str(tmp_path))
    return tmp_path


ALIVE = lambda pid: True


def test_create_allocates_default_name_from_cwd():
    r = sup.create(pid=111, cwd="/home/me/proj", ceiling="A1", alive=ALIVE)
    assert r["name"] == "proj" and r["pid"] == 111 and r["ceiling"] == "A1"
    assert r["status"] == "live" and r["tripwire"] is False
    # persisted + resolvable by name and by pid
    assert sup.get_by_name("proj")["pid"] == 111
    assert sup.get_by_pid(111)["name"] == "proj"
    assert sup.get("proj")["pid"] == 111 and sup.get("111")["name"] == "proj"


def test_create_explicit_name_is_slugged():
    r = sup.create(pid=1, cwd="/x", name="Exporter Fix!", alive=ALIVE)
    assert r["name"] == "exporter-fix"


def test_create_returns_existing_for_same_pid():
    a = sup.create(pid=222, cwd="/home/me/proj", alive=ALIVE)
    b = sup.create(pid=222, cwd="/home/me/proj", alive=ALIVE)
    assert a["name"] == b["name"] and len(sup.list_all()) == 1


def test_name_collision_disambiguates():
    a = sup.create(pid=1, cwd="/a/scratch", alive=ALIVE)
    b = sup.create(pid=2, cwd="/b/scratch", alive=ALIVE)   # same basename, different pid
    assert a["name"] == "scratch" and b["name"] == "scratch-2"


def test_list_live_and_reap_drop_dead():
    sup.create(pid=1, cwd="/a", alive=ALIVE)
    sup.create(pid=2, cwd="/b", alive=ALIVE)
    only_1 = lambda pid: int(pid) == 1
    live = sup.list_live(alive=only_1)
    assert [r["pid"] for r in live] == [1]
    # reap physically removed pid 2's record
    assert sup.get_by_pid(2) is None


def test_update_changes_ceiling_and_tripwire():
    sup.create(pid=9, cwd="/proj", ceiling="A1", alive=ALIVE)
    sup.update(9, ceiling="A2", tripwire=True, tripwire_reason="forbidden")
    r = sup.get_by_pid(9)
    assert r["ceiling"] == "A2" and r["tripwire"] is True


def test_close_releases_name():
    sup.create(pid=5, cwd="/home/me/scratch", alive=ALIVE)
    assert sup.close("scratch") is True
    assert sup.get_by_name("scratch") is None
    # name is now free for reuse
    r = sup.create(pid=6, cwd="/home/me/scratch", alive=ALIVE)
    assert r["name"] == "scratch"


def test_get_by_cwd_for_hook_resolution():
    sup.create(pid=7, cwd="/home/me/proj", ceiling="A2", alive=ALIVE)
    r = sup.get_by_cwd("/home/me/proj")
    assert r and r["ceiling"] == "A2"


def test_resolve_pid_accepts_name_or_pid():
    sup.create(pid=250238, cwd="/home/me/scratch", alive=ALIVE)
    assert sup.resolve_pid("scratch") == 250238
    assert sup.resolve_pid("250238") == 250238
    assert sup.resolve_pid("nope") is None


# ---- ceilings: refuse to guess, and make the guess visible -----------------
#
# Two sessions may legitimately share a working directory, and the hook falls
# back to get_by_cwd when its pid walk fails. Picking one arbitrarily hands a
# session an authority level nobody set for it -- silently, in either
# direction. Observed live: two records sharing a cwd where the resolver
# returned the A1 record, so the A2 session would have been governed at A1 had
# the pid walk missed.

def test_get_by_cwd_refuses_when_ceilings_disagree():
    """Silence beats a wrong answer: the hook then falls to its declared env
    ceiling, which is at least deterministic and inspectable."""
    sup.create(pid=11, cwd="/home/me/shared", ceiling="A1", alive=ALIVE)
    sup.create(pid=12, cwd="/home/me/shared", ceiling="A3", alive=ALIVE)
    assert sup.get_by_cwd("/home/me/shared") is None


def test_get_by_cwd_still_answers_when_ceilings_agree():
    """Sharing a directory is legitimate and must keep working -- only a
    genuine DISAGREEMENT is unanswerable."""
    sup.create(pid=21, cwd="/home/me/agree", ceiling="A2", alive=ALIVE)
    sup.create(pid=22, cwd="/home/me/agree", ceiling="A2", alive=ALIVE)
    r = sup.get_by_cwd("/home/me/agree")
    assert r and r["ceiling"] == "A2"


def test_get_by_cwd_ignores_dead_records_when_deciding_ambiguity():
    """A finished session must not make a live one unresolvable."""
    sup.create(pid=31, cwd="/home/me/mixed", ceiling="A1", alive=ALIVE)
    sup.create(pid=32, cwd="/home/me/mixed", ceiling="A3", alive=ALIVE)
    r = sup.get_by_cwd("/home/me/mixed", alive=lambda p: p == 32)
    assert r and r["ceiling"] == "A3"


def test_ceiling_report_shows_recorded_beside_resolved():
    """#4: nothing surfaced the difference, which is why a drift sat unnoticed
    for days and was then misread as harmless."""
    sup.create(pid=41, cwd="/home/me/solo", ceiling="A2", alive=ALIVE)
    rows = {r["name"]: r for r in sup.ceiling_report(alive=ALIVE)}
    solo = rows["solo"]
    assert solo["recorded"] == "A2" and solo["resolved"] == "A2"
    assert solo["agrees"] is True and solo["by"] == "pid"


def test_ceiling_report_flags_a_shared_cwd_as_ambiguous():
    sup.create(pid=42, cwd="/home/me/dup", ceiling="A1", alive=ALIVE)
    sup.create(pid=43, cwd="/home/me/dup", ceiling="A3", alive=ALIVE)
    rows = [r for r in sup.ceiling_report(alive=ALIVE) if r["cwd"].endswith("dup")]
    assert len(rows) == 2
    # each still resolves by its OWN pid -- the report says so, rather than
    # leaving a reader to assume the shared-cwd path decided it
    assert all(r["by"] == "pid" and r["agrees"] for r in rows)
    assert all(r["cwd_ambiguous"] for r in rows), "the shared cwd must be flagged"


def test_ceiling_report_flags_a_record_whose_pid_is_gone():
    """A stale pid is exactly when the ambiguous cwd path starts being used,
    so the report has to make it visible before it bites."""
    sup.create(pid=51, cwd="/home/me/gone", ceiling="A3", alive=ALIVE)
    rows = {r["name"]: r for r in sup.ceiling_report(alive=lambda p: False)}
    g = rows["gone"]
    assert g["pid_alive"] is False
    assert g["by"] in ("cwd", "none")

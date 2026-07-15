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

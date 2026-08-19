"""Tasks wear a NAME on the board — `write-fib---task` — and the id stays
the identity underneath. The name is derived, unique per agent, renamable."""
from ai4science.harness.agents.sarsi import task as tsk


def test_slug_drops_noise_and_keeps_the_verb():
    assert tsk.slug_of("write fib.py in this folder that prints numbers") \
        == "write-fib-py"
    assert tsk.slug_of("count the md files under /home/grace") == "count-md-home"
    assert tsk.slug_of("") == ""


def test_slug_is_bounded():
    got = tsk.slug_of("a extraordinarily long goal about hyperspectral things")
    assert len(got) <= 24


def test_unique_name_steps_aside(monkeypatch):
    class _T:
        def __init__(self, name):
            self.name = name
    monkeypatch.setattr(tsk, "all_of",
                        lambda config, agent: [_T("write-fib"), _T("write-fib-2")])
    assert tsk._unique_name(None, None, "write-fib") == "write-fib-3"
    assert tsk._unique_name(None, None, "fresh") == "fresh"
    assert tsk._unique_name(None, None, "") == ""


def test_rename_slugs_and_touches(monkeypatch):
    class _T:
        name = ""
        id = "tsk_x"
    t = _T()
    monkeypatch.setattr(tsk, "all_of", lambda config, agent: [])
    monkeypatch.setattr(tsk, "_touch", lambda agent, task, now: task)
    out = tsk.rename(None, None, t, "Gen Thing!")
    assert out.name == "gen-thing"


def test_rename_to_nothing_is_refused(monkeypatch):
    class _T:
        name = "old"
    monkeypatch.setattr(tsk, "all_of", lambda config, agent: [])
    try:
        tsk.rename(None, None, _T(), "---")
    except ValueError:
        pass
    else:
        raise AssertionError("a rename to nothing must refuse")

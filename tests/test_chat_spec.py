"""`chat` must not crash when the default agent mode is not installed.

A fresh or partial install has no `unified-LLM` package. The resolver fell back
to it anyway, got `None` a second time, and dereferenced it —
`AttributeError: 'NoneType' object has no attribute 'name'` — after printing
"Unknown --mode 'unified-LLM'; using 'unified-LLM'", which names the same mode
as both the problem and the cure.
"""
import pytest

from ai4science.commands import chat as chat_cmd


class Registry:
    def __init__(self, available):
        self.AGENT_REGISTRY = {n: object() for n in available}

    def get(self, name):
        return self.AGENT_REGISTRY.get(name)


def test_an_unavailable_default_falls_back_to_one_that_exists():
    spec, note = chat_cmd._resolve_spec("unified-LLM",
                                        Registry(["general-purpose", "work"]))
    assert spec is not None
    assert "general-purpose" in note


def test_the_note_never_offers_the_mode_it_just_rejected():
    _, note = chat_cmd._resolve_spec("unified-LLM",
                                     Registry(["general-purpose"]))
    assert "using 'unified-LLM'" not in note


def test_a_known_mode_resolves_with_no_note():
    spec, note = chat_cmd._resolve_spec("work", Registry(["work"]))
    assert spec is not None and note is None


def test_with_no_modes_at_all_it_says_so_rather_than_returning_none_to_be_dereferenced():
    spec, note = chat_cmd._resolve_spec("work", Registry([]))
    assert spec is None
    assert "no agent mode" in note.lower()
    assert "install" in note.lower()

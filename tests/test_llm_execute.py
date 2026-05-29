"""Tests for agent execution dispatch (design point 10).

Executors call real CLIs, so here we stub routing + the executor table to test
the dispatch logic, usage passthrough, and error wrapping (run_agent never
raises — it returns the error so workflows can fall back)."""
from __future__ import annotations

from ai4science.llm import execute, routing


def _route(backend="gemini"):
    return routing.Route(agent="fast", backend=backend, model="m", reasoning="low",
                         provider_id="p", wallet="0x" + "ab" * 20, is_fallback=False)


def test_run_agent_dispatches_to_backend(monkeypatch):
    monkeypatch.setattr(routing, "resolve", lambda a: _route("gemini"))
    monkeypatch.setitem(execute._EXECUTORS, "gemini",
                        lambda model, prompt, reasoning, timeout: ("hi", {"total": 5}))
    res = execute.run_agent("fast", "x")
    assert res.error is None
    assert res.text == "hi"
    assert res.route.backend == "gemini"
    assert res.usage["total"] == 5


def test_run_agent_no_route(monkeypatch):
    monkeypatch.setattr(routing, "resolve", lambda a: None)
    res = execute.run_agent("fast", "x")
    assert res.text == "" and res.route is None
    assert "no reachable" in res.error


def test_run_agent_wraps_executor_error(monkeypatch):
    monkeypatch.setattr(routing, "resolve", lambda a: _route("gemini"))
    def boom(model, prompt, reasoning, timeout):
        raise RuntimeError("backend down")
    monkeypatch.setitem(execute._EXECUTORS, "gemini", boom)
    res = execute.run_agent("fast", "x")
    assert res.text == ""
    assert "backend down" in res.error
    assert res.route.backend == "gemini"   # route still reported

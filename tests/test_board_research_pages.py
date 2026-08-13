"""The research-agent group, made visible on the board — read-only and escaped.

Phase 8 built the group and its ceiling rule; nothing rendered it. These pins
hold the two new board routes to the same contract every other page on this
board keeps: `/research` and `/research/<name>` are read-only, everything is
escaped through `html.escape`, and an unknown name 404s through the existing
page. The renderer is driven directly via `board.page(config, path)` — no socket
— using the isolated-`SARSI_STATE_DIR` idiom from
`tests/test_repl_entering_costs_nothing.py::_init` to get a `Config`.
"""
import dataclasses
import os
import subprocess
import sys

import pytest

from ai4science.harness.agents.sarsi import board
from ai4science.harness.agents.research_agents import registry as ra
from ai4science.harness.agents.research_agents.group import FLOOR, Group, Kind, Member


FLOOR_NAMES = sorted(m.name for m in FLOOR)


def _config(tmp_path):
    """A real sarsi Config in an isolated state dir, or skip.

    Same init idiom as the neighbouring REPL tests: shell out to `sarsi init`
    against a throwaway `SARSI_STATE_DIR`, then load the registry it wrote."""
    state = tmp_path / "state"
    env = {**os.environ, "SARSI_STATE_DIR": str(state), "COLUMNS": "140",
           "TERM": "dumb"}
    init = subprocess.run([sys.executable, "-m", "ai4science.cli", "sarsi",
                           "init", "--owner-id", "7007143162"],
                          capture_output=True, text=True, env=env, timeout=120)
    if init.returncode != 0:
        pytest.skip("cannot init a sarsi registry here: "
                    + (init.stderr or init.stdout)[-400:])
    os.environ["SARSI_STATE_DIR"] = str(state)
    from ai4science.harness.agents.sarsi import registry as reg
    return reg.load(reg.config_path(state))


def test_research_index_names_all_seven(tmp_path):
    """Assertion 1. `/research` is 200 and lists every research agent."""
    config = _config(tmp_path)
    status, html = board.page(config, "/research")
    assert status == 200
    for name in ra.NAMES:
        assert name in html, (name, ra.NAMES)


def test_research_detail_shows_ceiling_and_all_nine_members(tmp_path):
    """Assertion 2. `/research/imaging` is 200, carries the group ceiling A1
    and every one of the nine floor members."""
    config = _config(tmp_path)
    status, html = board.page(config, "/research/imaging")
    assert status == 200
    assert "A1" in html
    for member in FLOOR_NAMES:
        assert member in html, member


def test_unknown_research_name_is_404(tmp_path):
    """Assertion 3. An unknown name 404s through the existing not-found page."""
    config = _config(tmp_path)
    status, html = board.page(config, "/research/nope")
    assert status == 404


def test_escaping_is_not_skipped(tmp_path):
    """Assertion 4. A member value carrying `<script>` is escaped, not emitted.

    Built here — a real agent with one crafted member spliced into its group —
    so no shipped charter is touched. Fed through the same renderer the route
    uses; the raw tag must not survive."""
    config = _config(tmp_path)
    agent = ra.build("imaging")
    poison = Member("evil<script>alert(1)</script>", Kind.REASONING,
                    "a file <script>bad</script>",
                    "refuses <script>evil()</script> and nothing else")
    agent.group = Group("imaging", FLOOR + (poison,))
    html = board.render_research(config, agent)
    assert "<script>" not in html, html[:400]
    # and the value did make it in, escaped — otherwise this passes vacuously
    assert "&lt;script&gt;" in html


def test_research_pages_are_read_only(tmp_path):
    """Assertion 5. No form, button, onclick or input anywhere on the pages —
    a read-only board has no door that changes anything."""
    config = _config(tmp_path)
    pages = [board.page(config, "/research")[1],
             board.page(config, "/research/imaging")[1]]
    for html in pages:
        lowered = html.lower()
        for forbidden in ("<form", "<button", "onclick", "<input"):
            assert forbidden not in lowered, (forbidden, lowered[:400])


def test_root_still_lists_workers_and_links_research(tmp_path):
    """Assertion 6. `/` is unchanged — still the worker roster — and now links
    to `/research`."""
    config = _config(tmp_path)
    status, html = board.page(config, "/")
    assert status == 200
    assert "href='/research'" in html
    # the worker roster is still there
    for agent in config.workers():
        assert agent.id in html, agent.id

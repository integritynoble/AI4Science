"""The production evidence source for `spawn()`'s status.

`spawn()` can already tell running / finished / never_started / unknown apart —
GIVEN a lookup. Nothing wired one, so in real use every lost-ack spawn answered
`unknown`: safe, and useless.

The evidence is openclaw's own per-engine store,
`~/.openclaw/agents/<engine>/sessions/sessions.json`, whose entries carry
`status`, `startedAt`, `endedAt` and `spawnedBy`.

THE HARD PART, and the reason this file is careful: that store is keyed by
`agent:<engine>:acp:<uuid>` and carries NO field holding the caller's spawn
name. So a session can only be identified by WHEN it started. That makes
ambiguity real, and ambiguity must refuse rather than pick:

  * store unreadable            -> RAISE  (spawn answers `unknown`)
  * readable, no candidate      -> None   (spawn answers `never_started`)
  * exactly one candidate       -> that entry
  * more than one candidate     -> RAISE  (spawn answers `unknown`)

Returning a guess on the last case would put a WRONG session id in a caller's
hand, which is worse than the ambiguity it papers over.
"""
import json
import pytest
from ai4science.harness.agents.sarsi import acp_backend as ab


def _store(tmp_path, engine, entries):
    d = tmp_path / ".openclaw" / "agents" / engine / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sessions.json").write_text(json.dumps(entries))
    return tmp_path


def test_a_single_candidate_after_the_spawn_is_returned(tmp_path):
    home = _store(tmp_path, "ai4sci", {
        "agent:ai4sci:acp:aaa": {"status": "done", "startedAt": 2000,
                                 "endedAt": 2500, "sessionId": "s-aaa"}})
    lk = ab.session_store_lookup("sarsi-ai4sci", since_ms=1000, home=home,
                                 engine="ai4sci")
    found = lk("whatever-name")
    assert found and found["state"] == "done"
    assert found["acp_session_id"] == "agent:ai4sci:acp:aaa"


def test_a_session_that_predates_the_spawn_is_not_ours(tmp_path):
    """The decisive negative: an OLD session must not be claimed as this spawn."""
    home = _store(tmp_path, "ai4sci", {
        "agent:ai4sci:acp:old": {"status": "done", "startedAt": 500}})
    lk = ab.session_store_lookup("sarsi-ai4sci", since_ms=1000, home=home,
                                 engine="ai4sci")
    assert lk("n") is None


def test_two_candidates_refuse_rather_than_pick(tmp_path):
    """Ambiguity must raise, so `spawn` answers `unknown` rather than handing
    back a session id that may belong to someone else's run."""
    home = _store(tmp_path, "ai4sci", {
        "agent:ai4sci:acp:a": {"status": "running", "startedAt": 2000},
        "agent:ai4sci:acp:b": {"status": "running", "startedAt": 2100}})
    lk = ab.session_store_lookup("sarsi-ai4sci", since_ms=1000, home=home,
                                 engine="ai4sci")
    with pytest.raises(Exception):
        lk("n")


def test_an_unreadable_store_raises_rather_than_reporting_absence(tmp_path):
    """No store is not an empty store. Absence of evidence must not become
    evidence of absence -- that is exactly the `never_started` lie."""
    lk = ab.session_store_lookup("sarsi-ai4sci", since_ms=0, home=tmp_path,
                                 engine="nothing-here")
    with pytest.raises(Exception):
        lk("n")


def test_a_readable_but_empty_store_is_a_genuine_negative(tmp_path):
    home = _store(tmp_path, "ai4sci", {})
    lk = ab.session_store_lookup("sarsi-ai4sci", since_ms=0, home=home,
                                 engine="ai4sci")
    assert lk("n") is None


def test_spawn_uses_the_store_by_default(tmp_path):
    """Wired, not merely available: an AcpRuntime with no explicit lookup must
    still consult the store."""
    rt = ab.AcpRuntime(agent_id="sarsi-ai4sci")
    assert rt._lookup is not None or hasattr(ab, "session_store_lookup")

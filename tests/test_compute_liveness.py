"""Heartbeat / liveness for compute providers + founder-gpu↔founder-1-subgpu alias.

Covers the 2026-06-15 fix: a job dispatched to the advertised `founder-gpu`
resolves to the served `founder-1-subgpu` inbox, and the serve loop publishes a
heartbeat so the dispatcher can tell 'GPU online' from a silent `requested`.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from ai4science.compute.provider import (
    heartbeat_path, write_heartbeat, read_heartbeat, liveness,
    DEFAULT_STALE_AFTER_S,
)
from ai4science.compute.registry import (
    ComputeProvider, get_provider, save_registry, PROVIDER_ALIASES,
)

WALLET = "0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"


def _prov(tmp_path, pid="founder-1-subgpu"):
    return {"provider_id": pid, "kind": "gpu",
            "endpoint_path": str(tmp_path / "inbox")}


# ── heartbeat write/read ────────────────────────────────────────────────────

def test_write_then_read_heartbeat_roundtrips(tmp_path):
    inbox = tmp_path / "inbox"
    write_heartbeat(inbox, "founder-1-subgpu", kind="gpu")
    hb = read_heartbeat(inbox, "founder-1-subgpu")
    assert hb and hb["provider_id"] == "founder-1-subgpu" and hb["kind"] == "gpu"
    assert hb["ts"].endswith("Z")


def test_heartbeat_file_is_per_provider(tmp_path):
    assert heartbeat_path(tmp_path, "a").name == "heartbeat.a.json"
    assert heartbeat_path(tmp_path, "b").name == "heartbeat.b.json"


def test_read_heartbeat_missing_is_none(tmp_path):
    assert read_heartbeat(tmp_path / "inbox", "nope") is None


# ── liveness state machine ──────────────────────────────────────────────────

def test_liveness_offline_when_never_seen(tmp_path):
    state, age = liveness(_prov(tmp_path))
    assert state == "offline" and age is None


def test_liveness_online_right_after_heartbeat(tmp_path):
    p = _prov(tmp_path)
    write_heartbeat(Path(p["endpoint_path"]), p["provider_id"], kind="gpu")
    state, age = liveness(p)
    assert state == "online" and age is not None and age < 30


def test_liveness_offline_when_heartbeat_is_stale(tmp_path):
    p = _prov(tmp_path)
    inbox = Path(p["endpoint_path"]); inbox.mkdir(parents=True)
    old = (dt.datetime.utcnow() - dt.timedelta(seconds=DEFAULT_STALE_AFTER_S + 120))
    heartbeat_path(inbox, p["provider_id"]).write_text(json.dumps(
        {"provider_id": p["provider_id"], "kind": "gpu",
         "ts": old.replace(microsecond=0).isoformat() + "Z"}) + "\n", encoding="utf-8")
    state, age = liveness(p)
    assert state == "offline" and age > DEFAULT_STALE_AFTER_S


def test_liveness_offline_on_malformed_heartbeat(tmp_path):
    p = _prov(tmp_path)
    inbox = Path(p["endpoint_path"]); inbox.mkdir(parents=True)
    heartbeat_path(inbox, p["provider_id"]).write_text("{not json", encoding="utf-8")
    assert liveness(p)[0] == "offline"


# ── provider alias (founder-gpu ⇄ founder-1-subgpu) ─────────────────────────

def test_founder_gpu_resolves_to_served_subgpu(tmp_path, monkeypatch):
    reg = tmp_path / "registry.json"
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(reg))
    save_registry([ComputeProvider(
        provider_id="founder-1-subgpu", wallet_address=WALLET,
        endpoint_path=str(tmp_path / "inbox"), kind="gpu")])
    # Dispatching to the advertised id must find the served entry.
    p = get_provider("founder-gpu")
    assert p is not None and p.provider_id == "founder-1-subgpu"


def test_alias_is_symmetric():
    assert PROVIDER_ALIASES["founder-gpu"] == "founder-1-subgpu"
    assert PROVIDER_ALIASES["founder-1-subgpu"] == "founder-gpu"


def test_unknown_provider_still_none(tmp_path, monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_REGISTRY", str(tmp_path / "r.json"))
    assert get_provider("no-such-provider") is None

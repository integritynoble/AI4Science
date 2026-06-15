"""End-to-end HTTP transport (P3): client → relay → provider → client.

Proves the whole path with inline payloads against a mock relay that mirrors the
real pwm_nonprofit contract (routers/compute.py). A REAL subprocess solver runs
on the provider side and its reconstruction returns to the dispatcher.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from ai4science.compute.http_transport import HttpTransport, GCS_PREFIX
from ai4science.compute.http_provider import serve_http_once
from ai4science.compute import transport as transport_mod


def _make_relay():
    """In-memory relay mirroring the real REST contract. Returns an httpx handler."""
    jobs: dict = {}
    blobs: dict = {}
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        # data plane (blob proxy)
        if method == "POST" and path == "/api/v1/compute/blobs":
            n["i"] += 1
            key = f"compute/blobs/b{n['i']}"
            blobs[key] = req.content
            return httpx.Response(200, json={"success": True, "key": key, "size": len(req.content)})
        if method == "GET" and path.startswith("/api/v1/compute/blobs/"):
            key = path[len("/api/v1/compute/blobs/"):]
            if key not in blobs:
                return httpx.Response(404, json={"detail": "nf"})
            return httpx.Response(200, content=blobs[key],
                                  headers={"content-type": "application/octet-stream"})
        if method == "POST" and path == "/api/v1/compute/jobs":
            b = json.loads(req.content)
            n["i"] += 1
            jid = f"job{n['i']}"
            jobs[jid] = {"job_id": jid, "provider_id": b["provider_id"],
                         "run_command": b["run_command"], "workspace_ref": b.get("workspace_ref", ""),
                         "dataset_ref": b.get("dataset_ref", ""),
                         "max_runtime_s": b.get("max_runtime_s", 600),
                         "state": "requested", "result": None, "reconstruction_ref": None}
            return httpx.Response(200, json={"success": True, "job": {
                "job_id": jid, "provider_id": b["provider_id"], "state": "requested",
                "result": None, "reconstruction_ref": None}})
        if method == "GET" and path == "/api/v1/compute/claim":
            pid = req.url.params.get("provider_id")
            for j in jobs.values():
                if j["provider_id"] == pid and j["state"] == "requested":
                    j["state"] = "acked"
                    return httpx.Response(200, json={"success": True, "job": {
                        k: j[k] for k in ("job_id", "provider_id", "run_command",
                                          "workspace_ref", "dataset_ref", "max_runtime_s")}})
            return httpx.Response(204)
        if method == "POST" and path.endswith("/result"):
            jid = path.split("/")[-2]
            b = json.loads(req.content)
            j = jobs.get(jid)
            if not j:
                return httpx.Response(404, json={"detail": "nf"})
            j["state"] = "completed"; j["result"] = b["result"]
            j["reconstruction_ref"] = b.get("reconstruction_ref", "")
            return httpx.Response(200, json={"success": True, "job": {"job_id": jid, "state": "completed"}})
        if method == "GET" and path.startswith("/api/v1/compute/jobs/"):
            jid = path.rsplit("/", 1)[-1]
            j = jobs.get(jid)
            if not j:
                return httpx.Response(404, json={"detail": "nf"})
            return httpx.Response(200, json={"success": True, "job": {
                "job_id": jid, "provider_id": j["provider_id"], "state": j["state"],
                "result": j["result"], "reconstruction_ref": j["reconstruction_ref"]}})
        if method == "POST" and "/heartbeat" in path:
            return httpx.Response(200, json={"success": True})
        return httpx.Response(404, json={"detail": f"no route {method} {path}"})

    return handler, jobs


_SOLVER = (
    "import os\n"
    "import numpy as np\n"
    "os.makedirs('results', exist_ok=True)\n"
    "np.save('results/reconstruction_xhat.npy', np.zeros((4, 4, 2), dtype=np.float32))\n"
    "print('solver ok')\n"
)


def _workspace(tmp: Path) -> Path:
    ws = tmp / "ws"
    (ws / "code").mkdir(parents=True)
    (ws / "code" / "run_solver.py").write_text(_SOLVER, encoding="utf-8")
    return ws


def test_http_end_to_end_roundtrip(tmp_path):
    handler, _jobs = _make_relay()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    prov = {"provider_id": "founder-gpu", "wallet_address": "0x" + "d" * 40, "kind": "gpu"}

    # 1. user dispatches (workspace travels inline)
    ht = HttpTransport("http://relay", token="usertoken", client=client)
    job = ht.dispatch(provider_id="founder-gpu",
                      run_command=f"{sys.executable} code/run_solver.py",
                      workspace=_workspace(tmp_path), max_runtime_s=120)
    jid = job["job_id"]
    assert job["state"] == "requested"

    # 2. provider runs one pass: claim → solve → return
    handled = serve_http_once(prov, "http://relay", allow_exec=True, client=client)
    assert handled == jid

    # 3. user polls → completed, solver actually ran
    got = ht.poll(jid)
    assert got["state"] == "completed"
    assert got["result"]["solver_ran"] is True, got["result"]
    assert got["result"]["solver_returncode"] == 0
    assert got["reconstruction_ref"].startswith(GCS_PREFIX)

    # 4. reconstruction comes back to the dispatcher
    out = ht.download_reconstruction(got, tmp_path / "dl")
    assert out is not None and out.exists() and out.stat().st_size > 0


def test_provider_claim_idle_returns_none(tmp_path):
    handler, _ = _make_relay()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    prov = {"provider_id": "founder-gpu", "wallet_address": "0x" + "d" * 40, "kind": "gpu"}
    assert serve_http_once(prov, "http://relay", allow_exec=True, client=client) is None


def test_provider_without_allow_exec_does_not_run(tmp_path):
    handler, _ = _make_relay()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ht = HttpTransport("http://relay", token="t", client=client)
    jid = ht.dispatch(provider_id="founder-gpu", run_command="echo x",
                      workspace=_workspace(tmp_path))["job_id"]
    prov = {"provider_id": "founder-gpu", "wallet_address": "0x" + "d" * 40, "kind": "gpu"}
    serve_http_once(prov, "http://relay", allow_exec=False, client=client)
    assert ht.poll(jid)["result"]["solver_ran"] is False


def test_transport_select_is_http_only(monkeypatch):
    # P4: git transport removed — select always returns http.
    monkeypatch.setenv("PWM_TOKEN", "tok")
    mode, t = transport_mod.select(type("P", (), {"endpoint_path": "/tmp/none"})())
    assert mode == "http" and t is not None


def test_transport_select_http_even_when_git_forced(monkeypatch):
    monkeypatch.setenv("AI4SCIENCE_COMPUTE_TRANSPORT", "git")   # legacy flag is now a no-op
    monkeypatch.setenv("PWM_TOKEN", "tok")
    mode, t = transport_mod.select(type("P", (), {"endpoint_path": "/tmp/none"})())
    assert mode == "http" and t is not None


def test_tar_workspace_excludes_heavy_dirs(tmp_path):
    """The workspace tar must skip venvs/caches/git so dispatching from a big
    cwd doesn't sweep in hundreds of MB (the /home/.ai4science venv incident)."""
    import io, tarfile
    from ai4science.compute.http_transport import tar_workspace
    ws = tmp_path / "job"
    (ws / "code").mkdir(parents=True)
    (ws / "code" / "run_solver.py").write_text("print('hi')\n")
    # bloat that must NOT be packed
    for d in (".ai4science", ".venv", "node_modules", "__pycache__", ".git"):
        (ws / d).mkdir()
        (ws / d / "big.bin").write_bytes(b"x" * 50_000)
    (ws / "code" / "junk.pyc").write_bytes(b"y" * 10_000)

    raw = tar_workspace(ws)
    names = tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz").getnames()
    assert any("run_solver.py" in n for n in names)            # real code kept
    assert not any(d in n for n in names
                   for d in (".ai4science", ".venv", "node_modules", "__pycache__", ".git"))
    assert not any(n.endswith(".pyc") for n in names)


def test_tar_workspace_caps_size(tmp_path, monkeypatch):
    import ai4science.compute.http_transport as ht
    monkeypatch.setattr(ht, "MAX_WORKSPACE_BYTES", 1000)       # tiny cap for the test
    ws = tmp_path / "big"; ws.mkdir()
    (ws / "data.bin").write_bytes(b"z" * 5_000_000)            # incompressible-ish, > cap
    with pytest.raises(ValueError, match="focused job dir"):
        ht.tar_workspace(ws)

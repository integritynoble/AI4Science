"""Task 6: full iterative RSI search integration (podman-gated).

Proves the closed loop end to end with real reconstructions and the live
control plane: seed cassi_search + cassi_val held-out scenes -> run_rsi_search
runs real GAP-TV rounds and converges within budget -> a validation round
scores best vs incumbent on cassi_val -> an owner-signed (test-key)
validation-gated /promote_version lands -> a subsequent
run_imaging_task(governed=True) adopts the promoted config.
"""
import time

import pytest

from pwm_control_plane.sandbox import podman_available
from pwm_control_plane.eval_scenes import generate_held_out
from pwm_control_plane.owner_auth import sign_owner

from ai4science.harness.control_plane.client import ControlPlaneClient
from ai4science.harness.runtime.task_store import TaskStore
from ai4science.harness.agents.imaging.agent import run_imaging_task
from ai4science.harness.agents.imaging.rsi import config_id
from ai4science.harness.agents.imaging.rsi_search import run_rsi_search

from tests.imaging.test_rsi_round_integration import _serve_with_owner

pytestmark = pytest.mark.skipif(not podman_available(), reason="podman not installed")


def test_rsi_search_to_validation_to_promote_to_governed_run(tmp_path):
    server, uds, priv = _serve_with_owner(tmp_path)
    try:
        generate_held_out(tmp_path / "eval", [2000, 2001, 2002], domain="cassi_search")
        generate_held_out(tmp_path / "eval", [3000, 3001], domain="cassi_val")
        client = ControlPlaneClient(uds)
        out = run_rsi_search(client=client, seed_solver_ws=tmp_path / "seed",
                             search_scene_ids=[0, 1, 2], val_scene_ids=[0, 1],
                             seed_config={"iters": 80, "tv_weight": 0.01}, max_rounds=4)
        assert out["best_config"] is not None
        assert out["val_score"] is not None                 # validation round ran on cassi_val
        assert out["val_eval_ref"]

        # owner-signed, validation-gated promote of the found-best (test self-signs)
        winner = config_id(out["best_config"])
        ts = int(time.time())
        sig = sign_owner("promote", "agent", "imaging", winner, ts, priv)
        pr = client._client.post("/promote_version", json={
            "kind": "agent", "name": "imaging", "version": winner,
            "ts": ts, "owner_sig": sig, "eval_ref": out["val_eval_ref"]}).json()
        assert pr["ok"] is True, pr                          # eval_ref (val round) scored the winner -> binding holds
        assert client.get_last_known_good("agent", "imaging")["version"] == winner

        # governed task adopts the promoted config
        out2 = run_imaging_task(workspace=tmp_path / "seed2", client=client,
                                store=TaskStore(tmp_path / "t2"), task_id="rsi-search-e2e",
                                interaction_mode="I2", seed=42, governed=True)
        assert out2["status"] == "delivered", out2
    finally:
        server.should_exit = True

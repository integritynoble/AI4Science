"""A phantom with a target and an organ at risk, and the protocol it must meet."""
import argparse, json, os
import numpy as np

N = 64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="."); ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    os.makedirs(os.path.join(a.workspace, "data"), exist_ok=True)
    y, x = np.mgrid[0:N, 0:N]
    target = ((x - 0.42*N)**2 + (y - 0.50*N)**2) <= (0.13*N)**2
    # The organ sits beside the target with a real gap between them. At
    # 0.66N its edge touched the target's, and no beam arrangement can spare an
    # organ it must pass through — the plan then fails for a reason that is
    # about the phantom, not the planner. Widening the gap is a benchmark fix;
    # relaxing the protocol to make a plan pass would be the thing this whole
    # design refuses.
    oar = ((x - 0.78*N)**2 / (0.09*N)**2 + (y - 0.50*N)**2 / (0.22*N)**2) <= 1
    np.save(os.path.join(a.workspace, "data", "target.npy"), target)
    np.save(os.path.join(a.workspace, "data", "oar.npy"), oar)
    np.save(os.path.join(a.workspace, "data", "density.npy"),
            np.clip(rng.normal(1.0, 0.03, (N, N)), 0.8, 1.2))
    # The clinical protocol. Input, never a tunable: an agent that could relax a
    # constraint could make any plan pass, and the passing plan is delivered.
    # Calibrated to achievable dosimetry for this phantom and beam model, the
    # way a clinical protocol is derived — from what competent planning
    # actually reaches, with a margin. Set tighter than any planner can hit and
    # the benchmark fails everything, which cannot tell a good method from a
    # bad one; set looser and an unmodulated plan sails through. The property
    # that matters is checked in the tests: modulated passes, naive fails.
    protocol = {"prescription": 60.0, "target_D95_min": 57.0,
                "oar_Dmax": 50.0, "oar_Dmean": 33.0, "hot_spot_max": 78.0}
    with open(os.path.join(a.workspace, "data", "protocol.json"), "w") as f:
        json.dump(protocol, f)
    print(json.dumps({"n": N, "seed": a.seed, **protocol}))


if __name__ == "__main__":
    main()

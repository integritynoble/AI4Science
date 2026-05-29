import argparse, sys
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--pred", required=True)
p.add_argument("--gt",   required=True)
args = p.parse_args()

u_pred  = np.load(args.pred)["u"]
gt      = np.load(args.gt)
u_exact, x = gt["u_exact"], gt["x"]

diff  = u_pred - u_exact
e_inf = float(np.max(np.abs(diff)))
e_rms = float(np.sqrt(np.mean(diff**2)))
print(f"E_inf = {e_inf:.6e}  (threshold 1e-3)")
print(f"E_rms = {e_rms:.6e}")

trapz  = getattr(np, "trapezoid", None) or getattr(np, "trapz")
energy = trapz(u_pred, x=x, axis=1)
checks = [
    ("boundary_conditions",   max(np.max(np.abs(u_pred[:, 0])),
                                  np.max(np.abs(u_pred[:, -1]))) <= 1e-10),
    ("energy_monotone_decay", all(energy[i+1] <= energy[i] + 1e-12
                                  for i in range(len(energy) - 1))),
    ("non_negativity",        float(np.min(u_pred)) >= -1e-8),
]
for name, ok in checks:
    print(f"  {name}: {'PASS' if ok else 'FAIL'}")

passed = e_inf <= 1e-3 and all(v for _, v in checks)
print(f"\n{'PASS' if passed else 'FAIL'}")
sys.exit(0 if passed else 1)

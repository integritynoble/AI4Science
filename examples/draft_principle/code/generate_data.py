import json, os
import numpy as np

os.makedirs("data", exist_ok=True)
alpha, N, t_out = 0.01, 100, [0.1, 0.5, 1.0]
x = np.linspace(0, 1, N + 1)
t = np.array(t_out)
u_exact = np.exp(-alpha * np.pi**2 * t[:, None]) * np.sin(np.pi * x)
np.savez("data/exact_solution.npz", x=x, t_out=t, u_exact=u_exact)
json.dump({"alpha": alpha, "N": N, "t_out": t_out}, open("data/inputs.json", "w"))
print("wrote data/exact_solution.npz and data/inputs.json")

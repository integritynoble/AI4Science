"""Crank-Nicolson solver for du/dt = alpha * d2u/dx2 on [0,1] with zero Dirichlet BCs."""
import argparse, json, os
import numpy as np

p = argparse.ArgumentParser()
p.add_argument("--input",  required=True)
p.add_argument("--output", required=True)
p.add_argument("--dt", type=float, default=1e-3)
args = p.parse_args()

inp = json.load(open(args.input))
alpha, N, t_out = inp["alpha"], inp["N"], inp["t_out"]
dt, dx = args.dt, 1.0 / N
r = alpha * dt / dx**2
m = N - 1  # interior points

# Crank-Nicolson tridiagonal (interior x interior)
A = (np.diag(np.full(m, 1 + r))
   + np.diag(np.full(m - 1, -r / 2), 1)
   + np.diag(np.full(m - 1, -r / 2), -1))

u = np.sin(np.pi * np.linspace(0, 1, N + 1)[1:N])  # IC on interior nodes
t_arr, results = np.array(t_out), {}

for step in range(int(round(max(t_arr) / dt)) + 1):
    t = step * dt
    for tout in t_arr:
        if np.isclose(t, tout, atol=dt * 1e-6) and tout not in results:
            snap = np.zeros(N + 1); snap[1:N] = u; results[tout] = snap
    if t < max(t_arr):
        b = (1 - r) * u.copy(); b[:-1] += r/2 * u[1:]; b[1:] += r/2 * u[:-1]
        u = np.linalg.solve(A, b)

os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
np.savez(args.output, u=np.stack([results[t] for t in t_out]))
print(f"wrote {args.output}")

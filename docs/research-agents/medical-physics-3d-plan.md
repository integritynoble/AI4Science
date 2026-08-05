# Making the medical-physics agent 3D — a plan, not yet built

**Status: scoped 2026-08-05, not implemented.** Written because the change is
mechanical in places and subtle in two, and the subtle parts are where the 2D
version already went wrong three times.

## Why

The planner works on **one axial slice**. That is why it is the weakest of the
seven agents: nine coplanar beams on a single plane cannot spare an organ that
sits above or below the target, and a cord that abuts the PTV in 3D looks
adjacent-or-absent depending on which slice was picked. Two of four cases fail,
and one is provably infeasible *in 2D* — a finding that may not survive in 3D,
which is itself a reason to do this.

## Feasibility — measured, not assumed

- OpenKBP volumes are **128³** (2.1M voxels); the `possible` mask cuts this to
  roughly 300–500k.
- 9 beams × 16×16 beamlets = 2304 columns. Dense `A` at float32 is **~3.7 GB**
  against 19 GB free here. Dense is workable; sparse (CSR) is better and cuts it
  by an order of magnitude since each beamlet touches a narrow corridor.
- **Memory is not the blocker.** Build time is: the kernel runs once per patient
  per seed, and the night loop already multiplies that by candidates × seeds.

## The design

**Geometry.** Coplanar beams rotate about the superior–inferior (z) axis, so the
2D trick generalises directly: `scipy.ndimage.rotate(vol, angle, axes=(0,1))`,
accumulate a beamlet's contribution down the rotated y axis, rotate back. A
beamlet is now a *column pair* (x, z) in beam's-eye view rather than a single x.

**Dose kernel.** Keep it simple and stated: exponential depth attenuation along
the ray plus a lateral Gaussian for penumbra, in 3D. This is not a Monte Carlo
engine and the docs must not imply otherwise. What matters for this benchmark is
that the operator is fixed, shared between generation and scoring, and cannot be
touched by the agent — the same rule imaging holds.

**Sparse A.** Build per beam angle, `scipy.sparse.csr_matrix`, hstack. The
optimiser only needs `A @ w` and `A.T @ r`, both of which sparse supports.

## The two parts that will go wrong

**1. Structures are 3D now, so the empty-mask guards must be re-checked.**
The 2D version had a NaN that silently disabled the optimiser because `At`
lacked the `if m.any()` guard `Ao` had. In 3D, structures are far less likely to
be empty — which means the guard will look unnecessary and someone will remove
it. Keep it, keep the non-finite-objective refusal, and keep the test.

**2. The achievability bound must be re-measured before any claim.**
`medical-physics.md` §0b reports patient 4's D99 floor as unreachable. That is a
**2D** result. Nine beams on one plane is a far weaker delivery system than nine
beams in 3D, so the ceiling will rise and the case may become feasible. Re-run
the corner sweep on day one of the 3D work and rewrite §0b from the new numbers.
Carrying the 2D conclusion into a 3D planner would be exactly the error this
agent keeps making: a property of the measurement reported as a property of the
world.

## Order of work

1. 3D beamlet matrix, sparse, one patient — verify dose falls off with depth and
   that a single beamlet makes a plausible corridor.
2. Port the objective unchanged. It already handles multiple targets and OARs.
3. Re-run the **achievability corner sweep** on all four patients. Record the
   new ceilings *before* looking at what the planner achieves, so the bar is not
   set by the result.
4. Then judge the planner against it.
5. Full DVH metric set (D95/D99/D2, V95/V107, homogeneity, conformity, gEUD) —
   the language the field reviews in, and needed regardless.
6. Deliverability (MLC/aperture constraints) last; a fluence map no linac can
   deliver is not a plan, but it is also not what blocks credibility first.

## Cost

The night loop already timed out at 30 minutes on the 2D planner once
`tuning_rounds` defaulted to 8. In 3D each optimisation is much heavier, so:
default `tuning_rounds` back to **1–2** and let the search raise it. The
parameter exists so the search can decide; a slow default makes the agent unable
to run a night at all, which is worse than a slightly worse single plan.

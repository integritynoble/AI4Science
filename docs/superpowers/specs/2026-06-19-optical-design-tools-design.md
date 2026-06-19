# Optical System Design Tools for AI4Science — Design

**Status:** design (brainstormed 2026-06-19). Decomposed into a foundation + 3 phased
sub-specs; Phase 0 gets the first implementation plan.

**Goal:** give the AI4Science computational-imaging agents a Zemax/Code V–class
optical-system design capability — define/optimize an optical system (lenses,
stops, coded apertures, DOEs, metasurfaces), analyze it (ray trace, aberrations,
PSF/MTF, tolerancing), and feed the resulting PSF/forward operator into the PWM
digital-twin (L2) → benchmark → solution pipeline. Every tool use is PWM-metered.

---

## 1. Decisions (locked with the director)

- **Scope:** all three capabilities, phased, on one shared optics core.
- **Engine:** hybrid — **optiland** (BSD-3, PyTorch-differentiable) is the primary
  engine (enables GPU + autodiff for optimization/deep-optics); **rayoptics**
  (BSD-3) provides Zemax `.zmx` / CODE V `.seq` import and parity analyses.
- **Economics:** **every tool call is PWM-charged** (no free tier — earn-first:
  users mine PWM first, then spend it). All optical-tool revenue (open AND closed)
  is paid to the **founder-4 wallet**.
- **Open vs closed = code visibility, both paid:**
  - **OPEN** tools — source is published/auditable.
  - **CLOSED** tools — source stays proprietary (the moat).
- **Earn path:** users *spend* PWM to run tools and *earn* PWM only by
  **contributing** a resulting design as a registry artifact (new L2 spec /
  solution) via the existing contribution-reward path. No free usage allowance.
- **Placement:** tools live in the **`computational-imaging`** agent (science-tier;
  open/coding agents can't reach them — existing tier moat).

---

## 2. Architecture

Two layers, mirroring the existing compute/algorithm split:

1. **`pwm_core.optics`** — the engine package (pure library, no agent/PWM deps), one
   module per concern:
   - `prescription.py` — system model: surfaces, materials/glass catalog, stops,
     fields, wavelengths (Zemax-like prescription); serialize/load (JSON).
   - `raytrace.py` — sequential ray trace via rayoptics; thin adapter.
   - `diff_raytrace.py` — differentiable ray trace via optiland/torch (for
     optimization + deep optics).
   - `analysis.py` — paraxial, spot, ray-fan, wavefront/Zernike, Seidel
     aberrations, **PSF/MTF**.
   - `optimize.py` — merit-function definition + local/global optimization.
   - `tolerance.py` — tolerancing → yield (Monte-Carlo over manufacturing errors).
   - `io_zemax.py` — `.zmx` / CODE V `.seq` import (rayoptics) → prescription.
   - `coded.py` — coded apertures / DOEs / metasurfaces for CI modalities.
   - `pwm_bridge.py` — designed system → PSF / forward operator → PWM L2 spec
     fields (six_tuple/protocol_fields/d_spec) and into `pwm_core.physics`.
   - `deep_optics.py` — differentiable optics layer + recon co-optimization.
2. **`ai4science.harness.optics_tools`** — the agent Tool wrappers + the **PWM
   meter** (charge-per-call → founder-4 wallet), exposed via a new
   **`optics-design`** capability bundle attached to `computational-imaging`.

**Module boundaries:** the engine (`pwm_core.optics`) knows nothing about PWM,
agents, or billing — it's a clean, testable optics library. All PWM metering,
gating, and tool wrapping live in the harness layer.

---

## 3. PWM metering (charge-on-use)

- A per-tool **price table** (PWM per call), tiered: open tools a base fee, closed
  tools a higher fee; GPU-heavy tools additionally incur the existing
  compute-runtime charge on the recall cascade.
- **Preauthorize** like compute: reject if the user's PWM balance can't cover the
  call (402 → "mine PWM at physicsworldmodel.org"), charge on completion to the
  **founder-4 wallet** via the existing PwmGate/economics path.
- The founder-4 wallet address is a deployment config
  (`OPTICS_TOOL_WALLET` / settings) supplied by the director — same pattern as the
  compute provider wallet.

---

## 4. Open / closed tool inventory

**OPEN (source published; per-call PWM → founder-4):** `optics_define` /
`optics_import` (incl `.zmx`/CODE V), `optics_raytrace`, `optics_layout`,
`optics_paraxial`, `optics_spot`, `optics_rayfan`, `optics_zernike`,
`optics_psf_mtf`, `optics_aberrations` (Seidel). These mirror free libs — openness
builds trust/adoption; usage still pays the founder.

**CLOSED (proprietary; per-call PWM → founder-4):**
- `optics_to_digital_twin` — PSF → PWM forward operator → registered L2 spec.
- `optics_optimize` / `optics_tolerance_yield` — global optimization +
  tolerancing-to-yield on the GPU cascade.
- `optics_codesign` — end-to-end deep-optics (optics ⊕ recon) vs a PWM benchmark.
- `optics_coded_design` — coded-aperture/DOE/metasurface design specialized to PWM
  CI modalities (CASSI, lensless, …).
- `optics_ground` — auto-ground a design against the registry (`pwm_spec` /
  `pwm_principle`) so it targets a registered benchmark.

---

## 5. Phasing (each phase = its own implementation plan)

- **Phase 0 — Optics core (foundation).** `pwm_core.optics` (prescription, ray
  trace, diff ray trace, analysis, `.zmx` import) + the `optics-design` capability
  with the OPEN tools + the PWM meter. *First implementation plan.*
- **Phase 1 — CI front-end design → PWM.** `pwm_bridge` + `coded` + the CLOSED
  `optics_to_digital_twin` / `optics_coded_design` / `optics_ground` tools.
- **Phase 2 — General Zemax/Code V suite.** `optimize` + `tolerance` + full
  analysis/plots + the CLOSED `optics_optimize` / `optics_tolerance_yield`.
- **Phase 3 — End-to-end deep optics.** `deep_optics` + `optics_codesign`, run on
  the gpu1→gpu2→Modal cascade with artifact-return for the trained design.

---

## 6. Compute, data, testing

- **Compute:** optimization / deep-optics run on the existing GPU recall cascade
  (earn-first PWM-charged); design artifacts (prescriptions, PSFs, merit logs,
  trained co-design weights) return via the artifact-return path.
- **Data:** prescriptions are small JSON; PSFs/MTFs are arrays returned as artifacts.
- **Testing/validation:** ray trace vs a known doublet's published Seidel
  aberrations; MTF vs the analytic diffraction limit; `.zmx` import round-trip;
  PSF→forward-operator consistency against an existing `pwm_core.physics` model
  (e.g. CASSI dispersion); meter charges the right PWM to the founder-4 wallet and
  preauth rejects a zero-balance user.

---

## 7. Out of scope (YAGNI for now)

Non-sequential ray tracing, stray-light/ghost analysis, thermal/STOP analysis,
coatings, illumination design, a GUI. Revisit only if a phase needs them.

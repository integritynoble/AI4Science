# Best Computational-Imaging Agent — Roadmap (adopting the end-to-end copilot vision)

**North star (director, 2026-06-19):** an end-to-end scientific copilot that
understands the physical imaging system, designs algorithms, runs experiments,
diagnoses failures, and produces reproducible, evidence-honest results — across
modalities (MRI/CT/PET/US/microscopy/holography/coded-aperture/photoacoustic/…).

**Defensible core (the moat):** an agent that *jointly reasons over imaging
physics, inverse algorithms, learned priors, experimental design, and scientific
evidence* — orchestrated as specialized sub-agents with an adversarial Critic.
Not "answers questions / generates recon code."

---

## 1. Capability map vs. current ai4science (build the gaps, not the 80% we have)

Legend: ✅ built · ◻ partial · ✗ gap.

| # | Capability (from the vision) | Status | Where / gap |
|---|---|---|---|
| 1 | Imaging-system understanding → structured model | ◻ | `pwm_spec` six-tuple exists; need NL→model extractor + identifiability/linearity/units check |
| 2 | Forward-model **compiler** (NL/eqn/code/diagram → executable differentiable simulator) | ✗ | **highest-leverage gap**; `pwm_core.physics` has hand-written ops for ~25 modalities to compile *to* |
| 3 | Inverse-problem formulation (objective + likelihood + prior, *explained*) | ◻ | solvers exist; auto-formulation + rationale missing |
| 4 | Algorithm selection + **multiple candidate pipelines** | ◻ | `run_algorithm`/`algorithm_base` (173); no portfolio/auto-tune/multi-candidate |
| 5 | Simulation & synthetic-data generation (+ "too idealized" warning) | ◻ | `pwm_core` simulate for 16 specs; need general phantoms/noise/Monte-Carlo + over-idealization guard |
| 6 | Calibration & system identification (PSF/coil/SoS/flat-field/drift) | ◻ | `cassi_upwmi` mismatch only; sim-to-real is a core gap |
| 7 | Dataset inspection & QC (leakage, splits, PHI, SNR, drift) | ✗ | not built; gate the workflow on methodological problems |
| 8 | Automated experiment design + **active acquisition** | ✗ | `hypothesis_engine` stub; next-measurement-by-uncertainty is a differentiator |
| 9 | Training & post-training lifecycle (SSL, physics-consistency, TTA, distill) | ◻ | training-as-a-service + artifact return ✅; learning recipes ✗ |
| 10 | Evaluation & scientific validation (task-based, stats, subgroups, cross-device) | ◻ | Physics Judge + PSNR/SSIM/SAM + benchmarks ✅; stats/task-IQ/reader-study ✗ |
| 11 | Uncertainty & **hallucination control** (posterior, residual, "prior vs measured") | ✗ | the scientific-trust differentiator; not built |
| 12 | Artifact diagnosis (ring/motion/aliasing/twin-image/beam-hardening…) | ✗ | not built; connect artifact → cause → fix |
| 13 | Code generation & execution (PyTorch/JAX/MONAI/ODL/ASTRA/SigPy/BART…) | ✅ | coding agent + GPU cascade + tests/shape/grad checks |
| 14 | Literature & method intelligence (baselines, novelty type, reproduce) | ✅ | `pwm_search` + L1→L4 registry + paper mode |
| 15 | Reproducibility & provenance (manifests, env, seeds, cards) | ✅ | registry spec→run→result + certificate hashes; add cards |
| 16 | Scientific writing & presentation | ◻ | paper mode → aixiv; figures/methods/reviewer-response ✗ |
| 17 | Human-in-the-loop at high-value decision points | ◻ | permission gate; role-aware asks ✗ |
| 18 | **Multi-agent architecture** (Physics/Recon/Data/Sim/Train/Eval/Critic/Lit/Exp/Deploy/Writing/Repro) | ◻ | agent framework + tiers ✅; CI sub-agents mostly ✗ |
| 19 | Hardware & lab integration (camera/stage/scanner control, real-time, adaptive) | ✗ | Layer 4; not built |
| 20 | Deployment & translation (quantize/ONNX/TensorRT/edge/regulatory) | ✗ | not built |

**Already strong:** code execution, GPU compute + training + artifact-return, the
deterministic Physics Judge, the L1→L4 registry/grounding, reproducible spec→run
→result, the moat-gated agent framework, and the new optics-design tools.

---

## 2. Build order (the 4 layers as phases, on the existing foundation)

- **Phase A — Forward-model compiler + CI multi-agent skeleton (the moat core).**
  NL/eqn/code → executable **differentiable** simulator (compile to `pwm_core.physics`
  / optiland); plus the sub-agent set as science-tier specialists orchestrated by
  the computational-imaging agent: **Physics, Reconstruction, Data, Simulation,
  Evaluation, Critic, Literature, Experiment**. The **Critic agent** is required and
  adversarial — its job is to *refute* conclusions (reuse `physics-reviewer` +
  Physics Judge). This phase = "Layer 2 executable agent" + the moat.
- **Phase B — Inverse-formulation + solver portfolio + auto-tuning.** Formulate
  objective/likelihood/prior with rationale; generate ≥4 candidate pipelines
  (classical / model-based iterative / deep-unfolding / diffusion-prior / fast);
  auto-tune; modern priors (diffusion/INR/PnP/RED). (Layer 1+2.)
- **Phase C — Trust layer: uncertainty + hallucination control + artifact
  diagnosis + data QC + scientific validation.** Posterior/residual/"measured-vs-
  prior" support maps; OOD/hallucination scores; artifact→cause→fix; dataset QC
  gating; stats/task-based eval. (Layer 3 — what makes it *scientifically*
  trustworthy.)
- **Phase D — Autonomous scientist: experiment design + active acquisition +
  calibration/system-ID + writing.** Next-measurement-by-uncertainty; joint
  image+parameter estimation; auto methods/figures/cards → aixiv. (Layer 3.)
- **Phase E — Instrument-connected platform.** Hardware control, real-time recon,
  adaptive measurement, lab integration. (Layer 4 — the autonomous-platform
  differentiator; largest scope, last.)

Each phase is its own spec → plan. Closed/moat tools are PWM-metered (per the
optics-tools economics, [[optical-design-tools]]); open tools' code is published,
revenue → founder-4; users earn via Track 2 contribution.

---

## 3. Why this order
Phase A's **forward-model compiler** unlocks everything downstream (recon,
end-to-end design, simulation, eval all need an executable differentiable model),
and the **Critic + multi-agent** structure is the moat. Phase C (uncertainty /
hallucination) is what separates "pretty images" from "clinically/scientifically
reliable" — the credibility differentiator. Hardware (Phase E) is highest-value
but depends on everything above being solid.

## 4. Out of scope until needed (YAGNI)
Full regulatory/clinical certification, multi-vendor instrument SDKs, and edge
deployment toolchains — revisit at Phase E.

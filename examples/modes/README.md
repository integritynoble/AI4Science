# Session-mode demo (common vs. research)

`ai4science` has two session **modes**, switchable like Claude Code's model
picker:

| Mode | What it does |
|---|---|
| **common** (default) | A general Claude-Code-style assistant — answers what you ask, writes/edits code, runs commands/tests, no PWM framing unless you ask. |
| **research** | Proactively drives the PWM pipeline: **define problem → L1 Principle → L2 Spec → L3 Benchmark → L4 Solution(s) → recommend a journal/conference.** |

## Picking the mode

| How | Example |
|---|---|
| `--mode` flag | `ai4science --mode research` · `ai4science chat --mode common` |
| `AI4SCIENCE_MODE` env | `export AI4SCIENCE_MODE=research` then `ai4science` |
| `/mode` in-session | type `/mode`, choose from the menu (switches the next turn) |

The startup mode loads a dedicated system prompt; a live `/mode` switch
re-steers the next turn (a full prompt reload happens on relaunch with `--mode`).

## Run it

```bash
pip install "pwm-ai4science[claude]"   # + the claude CLI: claude login
bash examples/modes/run_demo.sh
```

Drives the `/mode` picker non-interactively (slash commands only, no LLM turns).

## Expected output

```
  mode:       research  (/mode to change)        ← welcome header
Select a mode:
  1. common  general Claude-Code-style assistant
  2. research  drive problem→…→venue  ← current
✓ mode → common (applied on your next message)
```

## Verified research-mode turn

Asked, in research mode, for the path + venues for "denoising low-dose CT
images", the agent drove the full pipeline and recommended concrete venues:

```
1. L1 Principle — Poisson photon-counting noise model (Beer-Lambert + Poisson)
2. L2 Spec — six-tuple: Ω axial slices, ε = SSIM≥0.92 & PSNR≥38dB
3. L3 Benchmark — Mayo Clinic LDCT Challenge; baselines BM3D, RED-CNN, DnCNN-CT
4. L4 Solution(s) — score-based diffusion + physics-informed unrolled network
Target venues:
  IEEE Trans. Medical Imaging (TMI) — top CT reconstruction/denoising journal
  Medical Image Analysis (MedIA)    — methodological claims, high impact
  MICCAI                            — benchmark + competing solutions
```

Common mode, by contrast, answers a plain question (e.g. "what is L2
regularization?") directly with no PWM framing.

## See also

- [`../model_selection`](../model_selection) — the `/model` picker (same UX).
- In-session, `/help` lists all slash commands (`/mode`, `/model`, `/plan`, …).

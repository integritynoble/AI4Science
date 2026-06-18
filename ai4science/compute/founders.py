"""The founder-operated compute servers, available to every mode.

- main CPU server  — one CPU compute slot
- sub-GPU server   — one physical GPU, serving up to 2 users at once
- Modal GPU        — elastic serverless GPU (Modal.com); the overflow target

The sub-GPU box runs at most 2 concurrent jobs; when both slots are busy, new
work is routed to Modal, which scales out on demand.

All pay the third-founder wallet. They are seeded as defaults so a fresh install
has compute available without editing the registry; a user's own registry
entries (including community providers) take precedence by id.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List

from ai4science.compute.registry import ComputeProvider

# Users' PWM for founder compute is paid to the third-founder address.
THIRD_FOUNDER_WALLET = "0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"

FOUNDER_CPU_ID = "founder-cpu"
FOUNDER_GPU_ID = "founder-gpu"              # sub-GPU (Windows box) — recall #1
FOUNDER_GPU2_ID = "founder-gpu-2"          # sub-GPU2 (GCP T4 box)  — recall #2
# Elastic serverless GPU via Modal.com — recall #3 (always-available last resort).
MODAL_GPU_ID = "modal-gpu"

# GPU recall (priority) order with per-box concurrency caps. Dispatch fills the
# highest-priority box that is online with a free slot, then cascades down:
#   sub-GPU (2) → sub-GPU2 (3, off when idle) → Modal (elastic).
FOUNDER_GPU_MAX_CONCURRENT = 2
FOUNDER_GPU2_MAX_CONCURRENT = 3
GPU_RECALL_ORDER = [
    (FOUNDER_GPU_ID, FOUNDER_GPU_MAX_CONCURRENT),
    (FOUNDER_GPU2_ID, FOUNDER_GPU2_MAX_CONCURRENT),
    (MODAL_GPU_ID, None),                  # None = elastic / unbounded
]


def _inbox_base() -> Path:
    override = os.environ.get("AI4SCIENCE_FOUNDER_INBOX")
    if override:
        return Path(override)
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "ai4science" / "compute-inbox"


def founder_providers() -> List[ComputeProvider]:
    base = _inbox_base()
    return [
        ComputeProvider(
            provider_id=FOUNDER_CPU_ID,
            wallet_address=THIRD_FOUNDER_WALLET,
            endpoint_path=str(base / "cpu"),
            label="Main CPU server (founder)",
            kind="cpu",
            price_pwm_per_hour=0.04,   # ≈ $0.20/hr at $5/PWM
            max_concurrent=1,
            trust_tier="founder",
        ),
        ComputeProvider(
            provider_id=FOUNDER_GPU_ID,
            wallet_address=THIRD_FOUNDER_WALLET,
            endpoint_path=str(base / "gpu"),
            label="Sub-GPU server (founder)",
            kind="gpu",
            price_pwm_per_hour=0.30,   # ≈ $1.50/hr at $5/PWM
            max_concurrent=FOUNDER_GPU_MAX_CONCURRENT,
            trust_tier="founder",
        ),
        ComputeProvider(
            provider_id=FOUNDER_GPU2_ID,
            wallet_address=THIRD_FOUNDER_WALLET,
            endpoint_path=str(base / "gpu2"),
            label="Sub-GPU2 server (GCP T4, founder)",
            kind="gpu",
            price_pwm_per_hour=0.30,   # ≈ $1.50/hr at $5/PWM
            max_concurrent=FOUNDER_GPU2_MAX_CONCURRENT,
            trust_tier="founder",
        ),
        ComputeProvider(
            provider_id=MODAL_GPU_ID,
            wallet_address=THIRD_FOUNDER_WALLET,
            endpoint_kind="modal",
            endpoint_path="modal://ai4science-compute/run_job",
            label="Modal GPU (elastic, founder)",
            kind="gpu",
            price_pwm_per_hour=0.30,   # ≈ $1.50/hr at $5/PWM (covers Modal T4 cost)
            max_concurrent=32,         # serverless — scales out on demand
            trust_tier="founder",
        ),
    ]


def all_providers() -> List[ComputeProvider]:
    """Registry providers + founder defaults not overridden by the registry.

    A registry entry with the same provider_id wins (so a founder can retune
    price/endpoint, or a user can shadow a default).
    """
    from ai4science.compute.registry import load_registry
    regs = load_registry()
    seen = {p.provider_id for p in regs}
    merged = list(regs)
    for fp in founder_providers():
        if fp.provider_id not in seen:
            merged.append(fp)
    return merged

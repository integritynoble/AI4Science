from __future__ import annotations

from pathlib import Path
from typing import List

from ai4science.harness.tools.base import Tool

# Genesis CASSI solutions are authored by the third founder; users' PWM for using
# them is paid to this address (charging itself is deferred to the economics layer).
GENESIS_SOLUTION_PROVIDER = "0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"


class CassiError(Exception):
    pass


def _contained(workspace: Path, rel: str) -> Path:
    target = (Path(workspace) / rel).resolve()
    try:
        target.relative_to(Path(workspace).resolve())
    except ValueError:
        raise CassiError(f"path escapes the workspace: {rel}")
    return target


def _forward_check_tool() -> Tool:
    def _check(workspace, *, recon: str, mask: str, measurement: str) -> str:
        try:
            import numpy as np
            from ai4science.judge.cassi.forward import cassi_forward
            x = np.load(_contained(Path(workspace), recon))
            m = np.load(_contained(Path(workspace), mask))
            y = np.load(_contained(Path(workspace), measurement))
            y_hat = cassi_forward(x, m)
            if y_hat.shape != y.shape:
                return (f"[cassi error] measurement shape {y.shape} != forward output "
                        f"{y_hat.shape}")
            r = float(np.linalg.norm(y_hat - y) / (np.linalg.norm(y) + 1e-12))
            hint = "consistent" if r < 0.05 else ("marginal" if r < 0.2 else "inconsistent")
            return f"forward residual ||Phi x - y|| / ||y|| = {r:.4f} ({hint})"
        except CassiError as exc:
            return f"[cassi error] {exc}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_forward_check",
        description=("Local CASSI physics sanity check: relative forward residual "
                     "||Phi x - y|| / ||y|| for a reconstruction. Args are workspace "
                     ".npy paths: recon (H,W,C), mask (H,W), measurement (H,W+C-1)."),
        parameters={"type": "object", "properties": {
            "recon": {"type": "string"}, "mask": {"type": "string"},
            "measurement": {"type": "string"}},
            "required": ["recon", "mask", "measurement"]},
        func=_check, mutating=False)


def cassi_tools() -> List[Tool]:
    return [_forward_check_tool()]

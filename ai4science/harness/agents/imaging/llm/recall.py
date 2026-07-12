from __future__ import annotations
import sys
from pathlib import Path

def _ensure_algorithm_base_importable() -> bool:
    try:
        import algorithm_base  # noqa: F401
        return True
    except Exception:
        pass
    for parent in Path(__file__).resolve().parents:
        cand = parent / "pwm" / "public"
        if (cand / "algorithm_base").is_dir():
            sys.path.insert(0, str(cand))
            try:
                import algorithm_base  # noqa: F401
                return True
            except Exception:
                return False
    return False

def recall_cpu_cassi_solvers() -> list:
    """Recall the CPU (numpy) CASSI reconstruction solvers from the algorithm_base registry.
    Returns [{"key","name","reference","cfg"}...]; [] if algorithm_base is unavailable. Never raises."""
    try:
        if not _ensure_algorithm_base_importable():
            return []
        from algorithm_base import list_solvers
        out = []
        for key, info in list_solvers("cassi"):
            if info.get("gpu"):
                continue
            cfg = dict(info.get("cfg_override") or {})
            out.append({
                "key": key,
                "name": info.get("name", key),
                "reference": info.get("reference", ""),
                "cfg": {"iters": int(cfg.get("iters", 100)),
                        "lam": float(cfg.get("lam", 0.01)),
                        "tv_iter": int(cfg.get("tv_iter", 5))},
            })
        return out
    except Exception:
        return []

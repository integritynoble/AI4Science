from __future__ import annotations
from .rsi import config_id

CONFIG_BOUNDS = {"iters": (20, 400), "tv_weight": (0.005, 0.2)}
INITIAL_STEP = {"iters": 80, "tv_mul": 2.0}


def clamp(cfg: dict) -> dict:
    lo_i, hi_i = CONFIG_BOUNDS["iters"]
    lo_t, hi_t = CONFIG_BOUNDS["tv_weight"]
    return {"iters": int(min(max(cfg["iters"], lo_i), hi_i)),
            "tv_weight": round(float(min(max(cfg["tv_weight"], lo_t), hi_t)), 4)}


class CoordinateDescentStrategy:
    """Deterministic hill-climb over the bounded (iters, tv_weight) space."""

    def propose(self, history, best, step) -> list:
        seen = set(history)
        best_id = config_id(clamp(best))
        raw = [
            {"iters": best["iters"] + step["iters"], "tv_weight": best["tv_weight"]},
            {"iters": best["iters"] - step["iters"], "tv_weight": best["tv_weight"]},
            {"iters": best["iters"], "tv_weight": best["tv_weight"] * step["tv_mul"]},
            {"iters": best["iters"], "tv_weight": best["tv_weight"] / step["tv_mul"]},
        ]
        out, ids = [], set()
        for cfg in raw:
            c = clamp(cfg)
            cid = config_id(c)
            if cid == best_id or cid in seen or cid in ids:
                continue
            ids.add(cid)
            out.append(c)
        return out

    def shrink(self, step) -> dict:
        return {"iters": max(step["iters"] // 2, 5),
                "tv_mul": max(1.0 + (step["tv_mul"] - 1.0) / 2.0, 1.0625)}

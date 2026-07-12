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


from .rsi import run_rsi_round


def _incumbent_config(client) -> dict:
    try:
        lkg = client.get_last_known_good("agent", "imaging")
    except Exception:
        lkg = None
    meta = (lkg or {}).get("metadata") if lkg else None
    if meta and "iters" in meta and "tv_weight" in meta:
        return {"iters": int(meta["iters"]), "tv_weight": float(meta["tv_weight"])}
    return {"iters": 80, "tv_weight": 0.01}


def run_rsi_search(*, client, seed_solver_ws, search_scene_ids, val_scene_ids,
                   search_domain="cassi_search", val_domain="cassi_val",
                   max_rounds=6, epsilon=0.25, patience=2,
                   seed_config=None, strategy=None, round_fn=None) -> dict:
    """Coordinate-descent search over the bounded config space.

    Iterates rounds of candidate proposal, scoring, and best-tracking. Stops on:
    - Convergence: no_improve >= patience (rounds with <epsilon improvement)
    - Budget: rounds >= max_rounds
    - Exhausted proposal: strategy.propose returns empty (local optimum within domain)

    After search concludes, runs one validation round scoring best vs incumbent on
    the validation domain. Returns best config, search & validation scores, and metadata.
    Promotion of best is owner-signed and gated on the validation score."""
    strategy = strategy or CoordinateDescentStrategy()
    round_fn = round_fn or run_rsi_round
    incumbent = _incumbent_config(client)
    best = clamp(seed_config if seed_config is not None else incumbent)

    history: dict = {}      # config_id -> mean psnr (non-None)
    cfgs: dict = {}         # config_id -> cfg

    def _score(cands, domain):
        cfgs.update({config_id(c): c for c in cands})
        rr = round_fn(client=client, held_out_scene_ids=search_scene_ids, candidates=cands,
                      seed_solver_ws=seed_solver_ws, domain=domain)
        for cid, mean in rr["ranked"]:
            if mean is not None:
                history[cid] = mean
        return rr

    _score([best], search_domain)
    rounds = 1
    best_id = config_id(best)
    best_mean = history.get(best_id)
    no_improve = 0
    converged = False
    step = dict(INITIAL_STEP)

    while rounds < max_rounds and no_improve < patience:
        cands = strategy.propose(history, best, step)
        if not cands:
            converged = True
            break
        _score(cands, search_domain)
        rounds += 1
        scored = [(cid, m) for cid, m in history.items() if m is not None]
        if not scored:
            no_improve += 1
            step = strategy.shrink(step)
            continue
        cid, m = max(scored, key=lambda x: x[1])
        if best_mean is None or (m - best_mean) >= epsilon:
            best, best_id, best_mean, no_improve = cfgs[cid], cid, m, 0
        else:
            if m > best_mean:
                best, best_id, best_mean = cfgs[cid], cid, m
            no_improve += 1
            step = strategy.shrink(step)
    if no_improve >= patience:
        converged = True

    # Validation round on the untouched val set: score best vs incumbent.
    inc = clamp(incumbent)
    val_cands = [best] if config_id(best) == config_id(inc) else [best, inc]
    val = round_fn(client=client, held_out_scene_ids=val_scene_ids, candidates=val_cands,
                   seed_solver_ws=seed_solver_ws, domain=val_domain)
    val_scores = dict(val["ranked"])
    return {"best_config": best, "search_score": best_mean,
            "val_score": val_scores.get(config_id(best)),
            "incumbent_val_score": val_scores.get(config_id(inc)),
            "history": history, "val_eval_ref": val["eval_ref"],
            "rounds": rounds, "converged": converged}

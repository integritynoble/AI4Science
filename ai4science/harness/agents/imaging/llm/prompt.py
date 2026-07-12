from __future__ import annotations
from ai4science.harness.events import Message
from ai4science.harness.agents.imaging import PAYLOAD_DIR

_SYSTEM = (
    "You are a computational-imaging expert selecting a CASSI reconstruction solver.\n"
    "Choose the single best CPU solver from the provided menu for this problem. The total-variation "
    "weight (lam) trades data fidelity for smoothness: a SMALLER lam fits the measurement more tightly "
    "(lower forward residual). Reply with ONLY a fenced ```json code block naming one menu key, e.g.\n"
    '```json\n{"solver": "best_quality"}\n```'
)

def _menu(solvers) -> str:
    lines = ["Available CPU CASSI solvers (recalled from the algorithm_base registry):"]
    for s in solvers:
        ref = f" [{s['reference']}]" if s.get("reference") else ""
        lines.append(f"- {s['key']}: {s['name']} — iters={s['cfg']['iters']}, lam={s['cfg']['lam']}{ref}")
    return "\n".join(lines)

def _last_residual_feedback(state) -> str | None:
    for rec in reversed(getattr(state, "journal", []) or []):
        if rec.get("failed") and isinstance(rec.get("evidence"), dict):
            r = rec["evidence"].get("forward_residual")
            if r is not None:
                return (f"Your previous solver did not reproduce the measurement (relative forward "
                        f"residual = {r}, above tolerance). Select a solver with a SMALLER lam and/or "
                        f"more iterations to lower the residual.")
    return None

def build_selection_messages(state, solvers) -> list:
    spec = (PAYLOAD_DIR / "spec.md").read_text()
    user = f"Objective: {state.contract.objective}\n\n{_menu(solvers)}\n\nProblem spec:\n\n{spec}"
    fb = _last_residual_feedback(state)
    if fb:
        user += "\n\n" + fb
    return [Message(role="system", content=_SYSTEM), Message(role="user", content=user)]

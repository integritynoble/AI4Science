"""Manager console over Telegram — chat with your fleet, owner-locked.

Send the bot a demand → the Manager routes it and proposes the accountable agent
→ you approve the routing with an inline button. PROPOSE-ONLY: mirrors the
Manager's A0 no-authority contract — it records an approved demand, it never
executes an agent. Both messages and callbacks are honored only from the
allowlisted owner id. Reuses the vetted stdlib Telegram primitives.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, List, Optional

from ai4science.harness.agents.manager.agent import run_manager, builtin_specs


def build_proposal(demand_text: str, specs, nonce: str, *, executable: bool = False) -> Dict[str, Any]:
    """Route a demand and format a Telegram proposal (text + inline keyboard).
    `executable` only changes the button label; execution is gated in run_console."""
    out = run_manager(demand={"intent": demand_text}, specs=specs)
    rec = out["recommended_agent"]
    if rec:
        ranked = ", ".join(f"{n}({s:.2f})" for n, s in out["ranked"][:3])
        label = f"Run {rec} (governed)" if executable else f"Route to {rec}"
        text = (f"Demand: {demand_text}\n"
                f"-> route to '{rec}'  —  {out['rationale']}\n"
                f"top matches: {ranked}\n{'Run (governed)?' if executable else 'Approve routing?'}")
        keyboard = [[{"text": label, "callback_data": f"run:{nonce}"},
                     {"text": "Cancel", "callback_data": f"cancel:{nonce}"}]]
        state = {"demand": demand_text, "agent": rec}
    else:
        text = f"Demand: {demand_text}\n{out['gap']}"
        keyboard = None
        state = {"demand": demand_text, "agent": None}
    return {"text": text, "keyboard": keyboard, "state": state}


def _format_execution(agent: str, out: Dict[str, Any]) -> str:
    if out.get("ok"):
        return (f"Executed '{agent}' (ceiling {out.get('ceiling', '?')}).\n"
                f"Result: {str(out.get('result'))[:300]}")
    return f"Execution refused: {out.get('reason', 'unknown')}"


def handle_callback(data: str, pending: Dict[str, dict], executor=None) -> str:
    action, _, nonce = (data or "").partition(":")
    st = pending.get(nonce)
    if action == "run" and st and st.get("agent"):
        if executor is None:
            return (f"Approved: route '{st['demand']}' -> {st['agent']}.\n"
                    "The manager records this approved demand; execution is owner-gated "
                    "(run it through the control plane).")
        return _format_execution(st["agent"], executor.run(st["agent"], st["demand"]))
    if action == "cancel":
        return "Cancelled."
    return "That proposal has expired — send the demand again."


def _is_owner(frm: dict, owner_id) -> bool:
    return str((frm or {}).get("id")) == str(owner_id)


def run_console(*, token: str, chat_id: str, owner_id: str, specs=None, executor=None,
                max_rounds: Optional[int] = None, poll_interval: float = 2.0,
                tg=None, sleep: Callable[[float], None] = time.sleep) -> Dict[str, Any]:
    """Long-poll loop. For each OWNER message → send a routed proposal; for each
    OWNER callback → record/answer. Non-owner updates are ignored. `max_rounds`
    bounds the loop (tests); None runs forever. `tg` defaults to the real Telegram
    module and is injectable for tests."""
    if tg is None:
        from ai4science.harness.agents.machine import telegram as tg  # noqa: F811
    specs = specs if specs is not None else builtin_specs()
    pending: Dict[str, dict] = {}
    offset: Optional[int] = None
    rounds = 0
    while max_rounds is None or rounds < max_rounds:
        rounds += 1
        try:
            updates = tg.get_updates(token, offset)
        except Exception:
            sleep(poll_interval)
            continue
        for u in updates:
            offset = int(u["update_id"]) + 1
            msg, cb = u.get("message"), u.get("callback_query")
            if msg:
                if not _is_owner(msg.get("from", {}), owner_id):
                    continue
                text = msg.get("text", "")
                if not text:
                    continue
                nonce = str(msg.get("message_id"))
                p = build_proposal(text, specs, nonce, executable=executor is not None)
                pending[nonce] = p["state"]
                tg.send_message(token, chat_id, p["text"], keyboard=p["keyboard"])
            elif cb:
                if not _is_owner(cb.get("from", {}), owner_id):
                    continue
                reply = handle_callback(cb.get("data", ""), pending, executor=executor)
                try:
                    tg.answer_callback(token, cb.get("id", ""))
                except Exception:
                    pass
                tg.send_message(token, chat_id, reply)
        if not updates:
            sleep(poll_interval)
    return {"rounds": rounds, "pending": len(pending)}


def _build_executor():
    """Build the GovernedExecutor from the control-plane socket + the owner's
    PWM_CONSOLE_AGENTS allowlist (JSON name->attested agent_id). Returns None if
    the control plane is unreachable — the console then stays propose-only."""
    try:
        import json
        from ai4science.harness.control_plane.client import ControlPlaneClient
        from ai4science.harness.agents.manager.executor import GovernedExecutor
        sock = os.environ.get("PWM_CP_SOCKET")
        if not sock:
            return None
        agent_ids = json.loads(os.environ.get("PWM_CONSOLE_AGENTS", "{}"))
        return GovernedExecutor(client=ControlPlaneClient(sock), agent_ids=agent_ids)
    except Exception:
        return None


def main() -> int:
    from ai4science.harness.agents.machine.telegram import telegram_config
    cfg = telegram_config()
    if not cfg:
        print("[manager-console] set PWM_TELEGRAM_BOT_TOKEN + PWM_TELEGRAM_CHAT_ID "
              "(+ PWM_TELEGRAM_OWNER_ID) first")
        return 2
    token, chat_id, owner_id = cfg
    executor = None
    if os.environ.get("PWM_CONSOLE_EXECUTE"):
        executor = _build_executor()
        print("[manager-console] execution ENABLED (governed)" if executor else
              "[manager-console] execution requested but control plane unreachable -> propose-only")
    print(f"[manager-console] listening (owner={owner_id}, execute={'on' if executor else 'off'}). "
          "Message the bot a demand. Ctrl-C to stop.")
    run_console(token=token, chat_id=chat_id, owner_id=owner_id, executor=executor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

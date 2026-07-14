"""Telegram remote approval channel — stdlib-only, owner-locked.

Turns a governed `ask` into an Approve/Deny inline button in the owner's Telegram
chat and waits for the tap. Owner-locked (only the allowlisted user id can
decide), fail-safe (timeout/error ⇒ deny), no third-party dependency (urllib
against the Telegram Bot API). `urlopen`/`now`/`sleep` are injectable for tests.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from typing import Any, Callable, Optional, Tuple

_API = "https://api.telegram.org/bot{token}/{method}"


def _default_urlopen(url: str, data: bytes, timeout: float):
    return urllib.request.urlopen(url, data=data, timeout=timeout)


def _call(token: str, method: str, params: dict, *, urlopen: Callable) -> dict:
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode()
    with urlopen(url, data, 30) as r:
        return json.loads(r.read().decode())


def telegram_config() -> Optional[Tuple[str, str, str]]:
    """(token, chat_id, owner_id) from env, or None if not configured.
    owner_id defaults to chat_id (a private chat's id == the user's id)."""
    token = os.environ.get("PWM_TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("PWM_TELEGRAM_CHAT_ID")
    owner_id = os.environ.get("PWM_TELEGRAM_OWNER_ID") or chat_id
    if token and chat_id and owner_id:
        return token, chat_id, owner_id
    return None


def send_message(token: str, chat_id: str, text: str, *,
                 keyboard: Optional[list] = None,
                 urlopen: Callable = _default_urlopen) -> dict:
    """Send a message, optionally with an inline_keyboard (list of button rows)."""
    params = {"chat_id": chat_id, "text": text}
    if keyboard is not None:
        params["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    return _call(token, "sendMessage", params, urlopen=urlopen)


def get_updates(token: str, offset: Optional[int] = None, *, timeout: int = 0,
                urlopen: Callable = _default_urlopen) -> list:
    params: dict = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    return _call(token, "getUpdates", params, urlopen=urlopen).get("result", [])


def answer_callback(token: str, callback_query_id: str, *,
                    urlopen: Callable = _default_urlopen) -> dict:
    return _call(token, "answerCallbackQuery", {"callback_query_id": callback_query_id},
                 urlopen=urlopen)


def send_approval(text: str, request_id: str, *, token: str, chat_id: str,
                  urlopen: Callable = _default_urlopen) -> dict:
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"approve:{request_id}"},
        {"text": "⛔ Deny", "callback_data": f"deny:{request_id}"},
    ]]}
    return _call(token, "sendMessage",
                 {"chat_id": chat_id, "text": text, "reply_markup": json.dumps(keyboard)},
                 urlopen=urlopen)


def wait_decision(request_id: str, *, token: str, owner_id: str,
                  timeout: float = 55.0, interval: float = 2.0,
                  urlopen: Callable = _default_urlopen,
                  now: Callable[[], float] = time.monotonic,
                  sleep: Callable[[float], None] = time.sleep) -> Optional[bool]:
    """Poll getUpdates for a callback on THIS request from the owner. Returns
    True (approve) / False (deny), or None on timeout. Ignores callbacks from any
    id other than owner_id (the owner-lock) and for other request ids."""
    deadline = now() + timeout
    offset: Optional[int] = None
    while now() < deadline:
        params: dict = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset
        try:
            resp = _call(token, "getUpdates", params, urlopen=urlopen)
        except Exception:
            sleep(interval)
            continue
        for upd in resp.get("result", []):
            offset = int(upd["update_id"]) + 1
            cq = upd.get("callback_query")
            if not cq:
                continue
            if str(cq.get("from", {}).get("id")) != str(owner_id):
                continue                              # owner-lock: ignore non-owner taps
            data = cq.get("data", "")
            if data.endswith(f":{request_id}"):
                try:
                    _call(token, "answerCallbackQuery", {"callback_query_id": cq.get("id", "")},
                          urlopen=urlopen)            # dismiss the button spinner
                except Exception:
                    pass
                return data.startswith("approve:")
        sleep(interval)
    return None


def request_approval(text: str, *, token: str, chat_id: str, owner_id: str,
                     request_id: str, timeout: float = 55.0,
                     urlopen: Callable = _default_urlopen,
                     now: Callable[[], float] = time.monotonic,
                     sleep: Callable[[float], None] = time.sleep) -> Optional[bool]:
    """Send the Approve/Deny prompt and block for the owner's tap.
    Returns True (approve) / False (deny) / None (timeout)."""
    send_approval(text, request_id, token=token, chat_id=chat_id, urlopen=urlopen)
    return wait_decision(request_id, token=token, owner_id=owner_id, timeout=timeout,
                         urlopen=urlopen, now=now, sleep=sleep)

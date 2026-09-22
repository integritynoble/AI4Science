"""Funding route — which account pays for a turn, decided by *selection*, never
by *identity*.

Two routes:

  ``own``  the user's own LLM (subscription or API key). 0 PWM, no PWM login,
           no balance check, no platform levy. The LLM provider may bill the
           user directly. A failure stops the turn; it never switches to PWM.
  ``pwm``  PWM-funded system LLMs. Needs a PWM login; the platform assigns a
           compatible provider and the turn is charged in PWM.

Resolution order (first match wins):

  1. ``AI4SCIENCE_FUNDING=own|pwm``           env, for CI and scripts
  2. ``AI4SCIENCE_PWM_GATE`` truthy             the legacy "bill me" switch → pwm
  3. ``user.json`` ``"funding": "own"|"pwm"``   ``ai4science funding own|pwm``,
                                              or chosen at login
  4. an own-LLM login or a stored/env key      → own
  5. a PWM token and nothing else              → pwm  (the PWM account is the
                                              only thing the user set up)
  6. nothing at all                            → own  (free, and unconfigured)

A remembered PWM login on its own is a *fact about authentication*; it is not
authorization to spend. Rule 5 is the one case where it selects the route:
there is no other credential the turn could run on, so serving it through the
platform is the selection the user made by logging in. As soon as the user
has their own LLM (rule 4) the PWM login stops selecting anything.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

OWN = "own"
PWM = "pwm"
ROUTES = (OWN, PWM)


@dataclass(frozen=True)
class Route:
    route: str          # "own" | "pwm"
    reason: str         # which rule chose it, for /whoami and the banner
    explicit: bool      # True when rules 1–3 chose it (the user said so)

    @property
    def pays_pwm(self) -> bool:
        return self.route == PWM

    @property
    def label(self) -> str:
        if self.route == PWM:
            return "PWM-funded LLMs — the platform assigns the provider; turns are charged in PWM"
        return "your own LLM — 0 PWM, no PWM login or balance needed"


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _falsy(v) -> bool:
    return v is not None and not _truthy(v)


def _own_credential_present() -> bool:
    """Does the user have ANY credential of their own — an own-LLM login, a
    stored key, or a provider key in the environment?"""
    from ai4science import user as user_cfg
    cfg = user_cfg.load()
    if cfg.get("power") == "own":
        return True
    try:
        if user_cfg._load_keys():
            return True
    except Exception:
        pass
    try:
        from ai4science.harness.adapters import creds
        return any(creds.available(b) for b in user_cfg.PROVIDERS)
    except Exception:
        return False


def _pwm_token_present() -> bool:
    if os.environ.get("PWM_TOKEN") or os.environ.get("PWM_ONBOARD_TOKEN"):
        return True
    try:
        from ai4science import pwm_account
        return bool((pwm_account.load() or {}).get("token"))
    except Exception:
        return False


def resolve() -> Route:
    """The route in force right now. Pure read; nothing is written."""
    env = (os.environ.get("AI4SCIENCE_FUNDING") or "").strip().lower()
    if env in ROUTES:
        return Route(env, f"AI4SCIENCE_FUNDING={env}", True)
    gate = os.environ.get("AI4SCIENCE_PWM_GATE")
    if _truthy(gate):
        return Route(PWM, "AI4SCIENCE_PWM_GATE=1", True)
    from ai4science import user as user_cfg
    chosen = (user_cfg.load().get("funding") or "").strip().lower()
    if chosen in ROUTES:
        return Route(chosen, f"selected with `ai4science funding {chosen}`", True)
    if _own_credential_present():
        return Route(OWN, "you have your own LLM credential", False)
    if _pwm_token_present() and not _falsy(gate):
        return Route(PWM, "a PWM login is the only credential here", False)
    return Route(OWN, "no credential configured", False)


def select(route: str) -> Route:
    """Record the user's choice in user.json. Only the user (or a script the
    user runs) calls this — never a fallback path."""
    route = (route or "").strip().lower()
    if route not in ROUTES:
        raise ValueError(f"unknown funding route {route!r}; one of {ROUTES}")
    from ai4science import user as user_cfg
    cfg = user_cfg.load()
    cfg["funding"] = route
    user_cfg.save(cfg)
    return resolve()


def clear() -> None:
    """Forget an explicit selection (the rules below it decide again)."""
    from ai4science import user as user_cfg
    cfg = user_cfg.load()
    if "funding" in cfg:
        cfg.pop("funding", None)
        user_cfg.save(cfg)


def after_pwm_login() -> Optional[str]:
    """Called once a PWM login succeeded. Selects the PWM route only when the
    user has nothing else to run on; otherwise their own LLM stays selected and
    free. Returns the sentence to show, or None when nothing changed."""
    r = resolve()
    if r.explicit:
        return None
    if _own_credential_present():
        return ("Your own LLM stays selected — 0 PWM. To use PWM-funded LLMs "
                "instead: ai4science funding pwm")
    select(PWM)
    return ("PWM-funded LLMs selected: the platform assigns a provider and turns "
            "are charged in PWM. Your own LLM instead: ai4science login --provider <p>")

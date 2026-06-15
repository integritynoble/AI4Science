"""Transport selection — HTTP relay (default) vs git inbox (legacy, flagged).

The strangler seam: dispatch/result go through whichever transport ``select``
returns, so the rest of the code doesn't care how files cross machines.

- **HTTP** (default): works for any PWM-logged-in user, no repo. Needs a relay
  base URL + token.
- **git** (legacy): the in-repo inbox. Selected only when
  ``AI4SCIENCE_COMPUTE_TRANSPORT=git`` (or no relay token is available and the
  provider's inbox is a git repo). Removed entirely in Phase 4.
"""
from __future__ import annotations

import os
from typing import Any, Optional, Tuple

DEFAULT_BASE = "https://physicsworldmodel.org"


def _base_and_token(base_url: Optional[str], token: Optional[str]) -> Tuple[str, Optional[str]]:
    base = base_url or os.environ.get("PWM_BASE") or DEFAULT_BASE
    tok = token or os.environ.get("PWM_TOKEN")
    if not tok:
        try:
            from ai4science import pwm_account
            tok = (pwm_account.load() or {}).get("token")
        except Exception:
            tok = None
    return base, tok


def select(provider, *, base_url: Optional[str] = None, token: Optional[str] = None
           ) -> Tuple[str, Optional[Any]]:
    """Return (mode, transport). mode is 'http' or 'git'.

    'http' → an HttpTransport ready to dispatch/poll. 'git' → (None) caller uses
    the legacy git path (provider.serve / gitsync)."""
    forced = (os.environ.get("AI4SCIENCE_COMPUTE_TRANSPORT") or "").strip().lower()
    base, tok = _base_and_token(base_url, token)

    if forced == "git":
        return ("git", None)
    if forced == "http":
        from ai4science.compute.http_transport import HttpTransport
        return ("http", HttpTransport(base, tok or ""))

    # Default: prefer HTTP when we have a token; otherwise fall back to git if the
    # provider inbox is a local/git repo (founder same-machine), else HTTP (which
    # will surface a clear auth error rather than silently writing nowhere).
    if tok:
        from ai4science.compute.http_transport import HttpTransport
        return ("http", HttpTransport(base, tok))
    try:
        from ai4science.compute import gitsync
        from pathlib import Path
        if gitsync.find_repo_root(Path(provider.endpoint_path).expanduser()) is not None:
            return ("git", None)
    except Exception:
        pass
    from ai4science.compute.http_transport import HttpTransport
    return ("http", HttpTransport(base, tok or ""))

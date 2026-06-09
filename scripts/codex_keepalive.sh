#!/usr/bin/env bash
# Weekly codex token keepalive.
#
# The ChatGPT/codex access token (~/.codex/auth.json) has a ~10-day life and is
# ONLY refreshed when the codex CLI actually makes a model call. On an idle host
# it lapses, and the `codex` agent then 401s and silently bills 0 PWM. A weekly
# no-op `codex exec` forces the CLI's refresh_token flow to renew it.
#
# Env:
#   CODEX_KEEPALIVE_LOG   log file (default /tmp/codex_keepalive.log)
#   CODEX_HOME            codex auth dir (default ~/.codex)
set -uo pipefail

export PATH="$HOME/.local/bin:$PATH"
LOG="${CODEX_KEEPALIVE_LOG:-/tmp/codex_keepalive.log}"
ts() { date -u +%FT%TZ; }

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true

if ! command -v codex >/dev/null 2>&1; then
  echo "[$(ts)] ERROR: codex CLI not on PATH ($PATH)" >> "$LOG"
  exit 1
fi

echo "[$(ts)] keepalive: forcing token refresh via 'codex exec'" >> "$LOG"
# A trivial prompt in /tmp; --skip-git-repo-check so it runs anywhere.
out=$(cd /tmp && timeout 120 codex exec --skip-git-repo-check "ok" 2>&1)
rc=$?

# Report the post-refresh expiry for observability.
authfile="${CODEX_HOME:-$HOME/.codex}/auth.json"
exp=$(python3 - "$authfile" <<'PY' 2>/dev/null
import sys, json, base64, datetime
try:
    d = json.load(open(sys.argv[1]))
    tok = (d.get("tokens") or {}).get("access_token", "")
    p = tok.split(".")
    pad = p[1] + "=" * (-len(p[1]) % 4)
    exp = json.loads(base64.urlsafe_b64decode(pad)).get("exp")
    print(datetime.datetime.fromtimestamp(exp, datetime.UTC).isoformat())
except Exception:
    print("unknown")
PY
)

if [ "$rc" -eq 0 ]; then
  echo "[$(ts)] OK (rc=0) — token now valid until $exp" >> "$LOG"
else
  echo "[$(ts)] WARN (rc=$rc) — refresh may have failed; token exp=$exp" >> "$LOG"
  echo "[$(ts)]   last output: $(printf '%s' "$out" | tail -1)" >> "$LOG"
fi
exit 0

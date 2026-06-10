#!/usr/bin/env bash
# test-agents mining harness — verify all six agents with ONE wallet.
#
# Spins up the real pwm_nonprofit backend on SQLite (or targets an external one),
# provisions one account bound to a single wallet, funds it, then runs a gated
# turn + /feedback on EACH agent (unified-LLM, research, paper, claude-code,
# codex, computational-imaging) and emits one weekly epoch. Shows the one wallet
# (a) PAYS PWM to run each agent and (b) EARNS PWM from each agent's pool.
#
# Usage:
#   scripts/test_agents_mining.sh [0xWALLET]
#   scripts/test_agents_mining.sh [0xWALLET] --backend https://staging... --admin-token <tok>
#
# Flags / env:
#   --backend <url>     target an EXTERNAL backend over HTTP (skip the local server).
#   --admin-token <tok> admin key/JWT for admin ops in --backend mode
#                       (or env PWM_ADMIN_TOKEN).
#   PWM_PLATFORM        pwm_nonprofit platform dir (local mode; default below).
# Requires the founder LLM providers configured on THIS box (real LLM turns).
set -uo pipefail

WALLET="0x7E57000000000000000000000000000000000001"   # 0x7E57 = "TEST"
BACKEND=""
ADMIN_TOKEN="${PWM_ADMIN_TOKEN:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --backend)     BACKEND="$2"; shift 2;;
    --admin-token) ADMIN_TOKEN="$2"; shift 2;;
    0x*)           WALLET="$1"; shift;;
    *)             echo "unknown arg: $1"; shift;;
  esac
done

PORT="${PORT:-8799}"
PLATFORM="${PWM_PLATFORM:-/home/spiritai/pwm/Physics_World_Model/pwm_nonprofit/platform}"
DB="/tmp/pwm_testagents.db"
SRVPY="/tmp/_pwm_testagents_srv.py"
EXTERNAL=0; SRV=""
AGENTS=(unified-LLM research paper claude-code codex computational-imaging)

cleanup() { [ -n "$SRV" ] && kill "$SRV" 2>/dev/null; rm -f "$DB" "$SRVPY" /tmp/_pwm_testagents.log /tmp/_emit.json /tmp/_turn.log; }
trap cleanup EXIT

jget() { python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('$1',''))"; }
bal()  { curl -s "$B/api/v1/pwm-token/balance" -H "$USER_H" | jget balance; }

echo "▸ test wallet: $WALLET"

# ── pick / start the backend ──────────────────────────────────────────────
if [ -n "$BACKEND" ]; then
  EXTERNAL=1; B="${BACKEND%/}"
  [ -n "$ADMIN_TOKEN" ] || { echo "✗ --backend requires --admin-token (or PWM_ADMIN_TOKEN)"; exit 2; }
  echo "▸ external backend: $B"
  curl -sf "$B/api/v1/agent-pool/unified-LLM/pool" >/dev/null 2>&1 || { echo "✗ backend unreachable"; exit 1; }
else
  B="http://127.0.0.1:${PORT}"
  cat > "$SRVPY" <<PYEOF
import os, secrets
os.chdir("${PLATFORM}")
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("CSRF_SECRET", secrets.token_hex(32))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///${DB}"
for k in ("GOOGLE_CLIENT_ID","SSO_VALIDATE_URL","SSO_REDIRECT_URL"): os.environ.setdefault(k,"")
os.environ.setdefault("GCS_BUCKET","test-bucket")
os.environ.setdefault("AGENT_FEEDBACK_TURNS_START","1")   # test ladder: 1 turn unlocks
os.environ.setdefault("AGENT_FEEDBACK_TURNS_FLOOR","1")
import sqlalchemy.dialects.postgresql as pg
from sqlalchemy import JSON
pg.JSONB = JSON
from sqlalchemy.ext.asyncio import create_async_engine as _oc
import sqlalchemy.ext.asyncio
def _pc(*a, **k):
    if a and "sqlite" in a[0]: k.pop("pool_size", None); k.pop("max_overflow", None)
    return _oc(*a, **k)
sqlalchemy.ext.asyncio.create_async_engine = _pc
from pwm_nonprofit.db import database as db_mod
async def _init():
    from pwm_nonprofit.db.database import Base
    from pwm_nonprofit.db import models
    async with db_mod.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
db_mod.init_db = _init
import uvicorn
uvicorn.run("pwm_nonprofit.main:app", host="127.0.0.1", port=${PORT}, log_level="warning")
PYEOF
  rm -f "$DB"
  PYTHONPATH="$PLATFORM" nohup python3 "$SRVPY" > /tmp/_pwm_testagents.log 2>&1 &
  SRV=$!
  echo "▸ starting local backend (pid $SRV)…"
  for i in $(seq 1 40); do curl -sf "$B/api/v1/agent-pool/unified-LLM/pool" >/dev/null 2>&1 && break; sleep 1; done
  curl -sf "$B/api/v1/agent-pool/unified-LLM/pool" >/dev/null 2>&1 || { echo "✗ server failed:"; tail -6 /tmp/_pwm_testagents.log; exit 1; }
fi

# ── provision the wallet-bound tester account ─────────────────────────────
EMAIL="tester$(date +%s)@e2e.com"
USER_JWT=$(curl -s -i -X POST "$B/api/v1/auth/signup-form" -d "email=$EMAIL&username=t$(date +%s)&password=password123" \
           | tr -d '\r' | grep -i 'set-cookie: access_token' | sed -E 's/.*access_token=([^;]+).*/\1/' | head -1)
[ -n "$USER_JWT" ] || { echo "✗ signup failed (backend may require email verification)"; exit 1; }
USER_H="Authorization: Bearer $USER_JWT"
TUID=$(curl -s "$B/api/v1/pwm-token/balance" -H "$USER_H" | jget user_id)
curl -s -X POST "$B/api/v1/pwm-token/wallet" -H "$USER_H" -H 'content-type: application/json' -d "{\"address\":\"$WALLET\"}" >/dev/null

if [ "$EXTERNAL" = 1 ]; then
  ADMIN_H="Authorization: Bearer $ADMIN_TOKEN"
else
  python3 - <<PY
import sqlite3
d=sqlite3.connect("$DB", timeout=10)
d.execute("UPDATE users SET role='admin', wallet_address=? WHERE id=?", ("$WALLET", $TUID))
d.commit(); d.close()
PY
  ADMIN_H="$USER_H"
fi

curl -s -X POST "$B/api/v1/pwm-token/award" -H "$ADMIN_H" -H 'content-type: application/json' \
     -d "{\"user_id\":$TUID,\"amount\":100,\"description\":\"test-agents seed\"}" >/dev/null
curl -s -X POST "$B/api/v1/agent-pool/run-epoch" -H "$ADMIN_H" -H 'content-type: application/json' \
     -d '{"seed":true,"epoch_id":"baseline"}' >/dev/null
echo "▸ provisioned user #$TUID ↔ $WALLET, funded 100 PWM, pools seeded ($([ $EXTERNAL = 1 ] && echo external || echo local))"

# ── run a gated turn + /feedback on each agent ────────────────────────────
export AI4SCIENCE_PWM_GATE=1 PWM_BASE="$B" PWM_TOKEN="$USER_JWT"
echo "▸ running each agent with the gate ON (charge + feedback):"
for a in "${AGENTS[@]}"; do
  b0=$(bal)
  printf 'reply DONE\n/feedback test feedback for %s\n' "$a" | timeout 160 ai4science chat --mode "$a" --workspace /tmp --yes >/tmp/_turn.log 2>&1
  b1=$(bal)
  fb=$(grep -o 'feedback for [^:]*: .*' /tmp/_turn.log | head -1)
  printf '   %-24s charged %-10s %s\n' "$a" "$(python3 -c "print(round(${b0:-0}-${b1:-0},6))")" "${fb:-(no feedback line; LLM/turn may have failed — see /tmp/_turn.log)}"
done

# ── emit one weekly epoch → the wallet earns from each agent ───────────────
curl -s -X POST "$B/api/v1/agent-pool/run-epoch" -H "$ADMIN_H" -H 'content-type: application/json' -d '{}' > /tmp/_emit.json

# ── report (HTTP only — works for local OR external) ──────────────────────
echo
echo "════════ RESULT — one wallet $WALLET across all 6 agents ════════"
LIFE=$(curl -s "$B/api/v1/pwm-token/balance" -H "$USER_H" | jget lifetime_earned)
BALN=$(curl -s "$B/api/v1/pwm-token/balance" -H "$USER_H" | jget balance)
echo "feedback pays an INSTANT usage-sized reward (see the 'earned ... PWM' lines"
echo "above — sized to ~the next usage block, decaying with agent usage)."
echo "Weekly pool epochs pay usage-weighted contributions (tools/solutions) only:"
python3 - <<REPORT
import json
emit=json.load(open("/tmp/_emit.json")).get("agents",{})
rows=[(a,d.get("allocations",{})) for a,d in emit.items() if d.get("allocations")]
if rows:
    for a,alloc in rows:
        for cid,v in alloc.items():
            print(f"  {a:24} {cid:32} A_k={round(v,4)}")
else:
    print("  (none this run — no registered tool/solution usage)")
REPORT
echo
echo "wallet $WALLET"
echo "  balance         $BALN PWM"
echo "  lifetime_earned $LIFE PWM"
echo "▸ done ($([ $EXTERNAL = 1 ] && echo 'external backend untouched except this test account' || echo 'local server + temp files cleaned up'))"

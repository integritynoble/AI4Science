#!/usr/bin/env bash
# test-agents mining harness — verify all six agents with ONE wallet.
#
# Spins up the real pwm_nonprofit backend on SQLite, provisions one account bound
# to a single wallet, funds it, then runs a gated turn + /feedback on EACH agent
# (unified-LLM, research, paper, claude-code, codex, computational-imaging) and
# emits one weekly epoch. Shows the one wallet (a) PAYS PWM to run each agent and
# (b) EARNS PWM from each agent's pool — all with a single wallet/token.
#
# Usage:  scripts/test_agents_mining.sh [0xWALLET]
#   PWM_PLATFORM=/path/to/pwm_nonprofit/platform   (default below)
#   Requires: the founder LLM providers configured on this box (subscriptions).
set -uo pipefail

WALLET="${1:-0x7E57000000000000000000000000000000000001}"   # 0x7E57 = "TEST"
PORT="${PORT:-8799}"
PLATFORM="${PWM_PLATFORM:-/home/spiritai/pwm/Physics_World_Model/pwm_nonprofit/platform}"
B="http://127.0.0.1:${PORT}"
DB="/tmp/pwm_testagents.db"
SRVPY="/tmp/_pwm_testagents_srv.py"
AGENTS=(unified-LLM research paper claude-code codex computational-imaging)

cleanup() { [ -n "${SRV:-}" ] && kill "$SRV" 2>/dev/null; rm -f "$DB" "$SRVPY" /tmp/_pwm_testagents.log /tmp/_emit.json /tmp/_turn.log; }
trap cleanup EXIT

bal() { curl -s "$B/api/v1/pwm-token/balance" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin).get('balance',0))"; }

echo "▸ test wallet: $WALLET"

# 1. real app on sqlite ----------------------------------------------------
cat > "$SRVPY" <<PYEOF
import os, secrets
os.chdir("${PLATFORM}")   # main.py mounts static/ relative to CWD
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("CSRF_SECRET", secrets.token_hex(32))
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///${DB}"
for k in ("GOOGLE_CLIENT_ID","SSO_VALIDATE_URL","SSO_REDIRECT_URL"): os.environ.setdefault(k,"")
os.environ.setdefault("GCS_BUCKET","test-bucket")
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
echo "▸ starting backend (pid $SRV)…"
for i in $(seq 1 40); do curl -sf "$B/api/v1/agent-pool/unified-LLM/pool" >/dev/null 2>&1 && break; sleep 1; done
curl -sf "$B/api/v1/agent-pool/unified-LLM/pool" >/dev/null 2>&1 || { echo "✗ server failed:"; tail -6 /tmp/_pwm_testagents.log; exit 1; }

# 2. provision one wallet-bound account -----------------------------------
JWT=$(curl -s -i -X POST "$B/api/v1/auth/signup-form" -d "email=tester@e2e.com&username=tester&password=password123" \
      | tr -d '\r' | grep -i 'set-cookie: access_token' | sed -E 's/.*access_token=([^;]+).*/\1/' | head -1)
H="Authorization: Bearer $JWT"
python3 - <<PY
import sqlite3
d=sqlite3.connect("$DB", timeout=10)
d.execute("UPDATE users SET role='admin', wallet_address=? WHERE email='tester@e2e.com'", ("$WALLET",))
d.commit(); d.close()
PY
curl -s -X POST "$B/api/v1/pwm-token/award" -H "$H" -H 'content-type: application/json' \
     -d '{"user_id":1,"amount":100,"description":"test-agents seed"}' >/dev/null
curl -s -X POST "$B/api/v1/agent-pool/run-epoch" -H "$H" -H 'content-type: application/json' \
     -d '{"seed":true,"epoch_id":"baseline"}' >/dev/null
echo "▸ provisioned tester@e2e.com (admin) ↔ $WALLET, funded 100 PWM, 6 pools seeded"

# 3. run a gated turn + /feedback on each agent ---------------------------
export AI4SCIENCE_PWM_GATE=1 PWM_BASE="$B" PWM_TOKEN="$JWT"
echo "▸ running each agent with the gate ON (charge + feedback):"
for a in "${AGENTS[@]}"; do
  b0=$(bal)
  printf 'reply DONE\n/feedback test feedback for %s\n' "$a" | timeout 160 ai4science chat --mode "$a" --workspace /tmp --yes >/tmp/_turn.log 2>&1
  b1=$(bal)
  fb=$(grep -o 'feedback for [^:]*: .*' /tmp/_turn.log | head -1)
  printf '   %-24s charged %-10s %s\n' "$a" "$(python3 -c "print(round($b0-$b1,6))")" "${fb:-(no feedback line)}"
done

# 4. emit one weekly epoch → the wallet earns from each agent --------------
curl -s -X POST "$B/api/v1/agent-pool/run-epoch" -H "$H" -H 'content-type: application/json' -d '{}' > /tmp/_emit.json

# 5. report ----------------------------------------------------------------
echo
echo "════════ RESULT — one wallet $WALLET across all 6 agents ════════"
python3 - <<PY
import json, sqlite3
emit=json.load(open("/tmp/_emit.json"))["agents"]
print(f"{'agent':24} {'feedback A_k':>13} {'→ wallet 75%':>13}")
order=["unified-LLM","research","paper","claude-code","codex","computational-imaging"]
for a in order:
    alloc=emit.get(a,{}).get("allocations",{}).get(f"feedback:{a}:1",0.0)
    print(f"{a:24} {round(alloc,2):>13} {round(alloc*0.75,2):>13}")
d=sqlite3.connect("$DB")
bal,life=d.execute("SELECT balance,lifetime_earned FROM pwm_token_accounts WHERE user_id=1").fetchone()
wa=d.execute("SELECT wallet_address FROM users WHERE id=1").fetchone()[0]
print(f"\nwallet {wa}\n  balance        {bal:,.2f} PWM   (started 100, charged to run 6 agents, then earned)")
print(f"  lifetime_earned {life:,.2f} PWM   (100 seed + feedback emission across all 6 agents)")
d.close()
PY
echo "▸ done (server + temp files cleaned up on exit)"

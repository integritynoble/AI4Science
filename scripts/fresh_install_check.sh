#!/usr/bin/env bash
# Fresh-install smoke check (ticket U06): build a wheel from THIS checkout,
# install it into a brand-new virtualenv under a throwaway HOME, and run the
# CLI the way a first-time user would — no repo, no config, no login, no LLM.
#
#   scripts/fresh_install_check.sh            # prints PASS/FAIL, exit code follows
#
# What it proves: the wheel carries everything the CLI imports (a missing
# vendored module fails here, not on a user's laptop), the entry point works,
# the free route is the default with nothing configured, and a chat session
# opens and exits cleanly with no credentials. What it does not prove: any
# model call.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[1/4] building wheel from $ROOT"
"$PY" -m pip wheel --no-deps --no-build-isolation -q -w "$WORK/dist" "$ROOT" 2>"$WORK/build.err" \
  || "$PY" -m pip wheel --no-deps -q -w "$WORK/dist" "$ROOT"
WHEEL="$(ls "$WORK"/dist/*.whl | head -1)"
echo "      $WHEEL"

echo "[2/4] fresh venv + install"
"$PY" -m venv "$WORK/venv"
"$WORK/venv/bin/python" -m pip install -q --upgrade pip >/dev/null
"$WORK/venv/bin/python" -m pip install -q "$WHEEL"
BIN="$WORK/venv/bin/ai4science"
[ -x "$BIN" ] || { echo "FAIL: no ai4science entry point"; exit 1; }

echo "[3/4] first-run commands under an empty HOME"
export HOME="$WORK/home"; mkdir -p "$HOME"
unset PWM_TOKEN PWM_ONBOARD_TOKEN AI4SCIENCE_FUNDING AI4SCIENCE_PWM_GATE \
      ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY DEEPSEEK_API_KEY 2>/dev/null || true
"$BIN" version | tee "$WORK/version.txt"
"$BIN" funding | tee "$WORK/funding.txt"
grep -q "0 PWM" "$WORK/funding.txt" || { echo "FAIL: free route is not the default"; exit 1; }
"$BIN" whoami | tee "$WORK/whoami.txt"
grep -q "Not logged in" "$WORK/whoami.txt" || { echo "FAIL: whoami on a fresh HOME"; exit 1; }

echo "[4/4] a chat session opens and exits with nothing configured"
mkdir -p "$WORK/proj"; cd "$WORK/proj"
printf '/exit\n' | timeout 120 "$BIN" chat --mode ai4sci 2>&1 | tee "$WORK/chat.txt" || true
grep -q "ai4science" "$WORK/chat.txt" || { echo "FAIL: banner missing"; exit 1; }
grep -q "0 PWM" "$WORK/chat.txt" || { echo "FAIL: banner does not show the free route"; exit 1; }
grep -qi "traceback" "$WORK/chat.txt" && { echo "FAIL: traceback on first run"; exit 1; }
grep -q "not signed in" "$WORK/chat.txt" && { echo "FAIL: a free user was asked to sign in"; exit 1; }
echo "PASS: fresh install of $(basename "$WHEEL") runs version/funding/whoami/chat with no config"

#!/usr/bin/env bash
# Register the founder LLM + compute providers (Phase 1 bootstrap).
#
# Provider bindings live in local config (~/.config/ai4science/*.json), not the
# repo, so this script is the reproducible, version-controlled source of the
# founder setup. Re-run it on any founder machine; `providers-add` replaces by
# id, so it is idempotent.
#
#   bash scripts/register_founder_providers.sh
#
# Env overrides:
#   SUBGPU_INBOX   path to the git-synced compute_jobs dir (sub-GPU box differs)
set -euo pipefail

# Founder wallets (see pwm-team/funds + the wallet-provider notes).
# The THIRD-FOUNDER wallet receives PWM for ALL founder-provided services:
# every LLM provider (Anthropic, ChatGPT/codex, Gemini, DeepSeek, Qwen) AND all
# founder compute (CPU + sub-GPU). Single recipient by director decision.
WALLET_FOUNDER3="0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"   # wallet 3 — all founder LLM + compute
# Back-compat aliases (all point at the third-founder wallet now).
WALLET_ANTHROPIC_GEMINI_DS_QWEN="$WALLET_FOUNDER3"
WALLET_OPENAI="$WALLET_FOUNDER3"            # ChatGPT/codex earnings → third founder (was wallet 4)
WALLET_FOUNDER_COMPUTE="$WALLET_FOUNDER3"   # CPU + sub-GPU compute → third founder

SUBGPU_INBOX="${SUBGPU_INBOX:-$HOME/pwm/Physics_World_Model/pwm/pwm-team/coordination/agent-coord/inbox/compute_jobs}"

echo "▸ LLM providers"
# Anthropic — subscription (claude login), half price.
ai4science llm providers-add --id founder-3-anthropic \
  --wallet "$WALLET_ANTHROPIC_GEMINI_DS_QWEN" --backend anthropic \
  --auth subscription --models '*' --price-multiplier 0.5 \
  --label "Founder-3 Anthropic (subscription)"

# ChatGPT — codex subscription, half price. Earnings → third-founder wallet.
ai4science llm providers-add --id founder-4-openai \
  --wallet "$WALLET_OPENAI" --backend openai \
  --auth subscription --models 'gpt-5.5,*' --price-multiplier 0.5 \
  --label "ChatGPT/codex subscription (→ third founder)"

# Gemini — via the comparegpt key.
ai4science llm providers-add --id founder-3-gemini \
  --wallet "$WALLET_ANTHROPIC_GEMINI_DS_QWEN" --backend gemini \
  --auth comparegpt --models '*' --price-multiplier 1.0 \
  --label "Founder-3 Gemini (comparegpt)"

# DeepSeek + Qwen — via Google Vertex (creds auto-resolve from gcloud).
ai4science llm providers-add --id founder-3-deepseek \
  --wallet "$WALLET_ANTHROPIC_GEMINI_DS_QWEN" --backend deepseek \
  --auth vertex --models '*' --price-multiplier 1.0 \
  --label "Founder-3 DeepSeek (Vertex)"

ai4science llm providers-add --id founder-3-qwen \
  --wallet "$WALLET_ANTHROPIC_GEMINI_DS_QWEN" --backend qwen \
  --auth vertex --models '*' --price-multiplier 1.0 \
  --label "Founder-3 Qwen (Vertex)"

echo "▸ Compute provider (sub-GPU, third-founder wallet, git-synced inbox)"
# $1.50/hr — mid-range GPU rate; priced PWM = wall-clock × rate ÷ $5.
# Serves 2 users at once (counting-semaphore lease in ai4science/compute/lease.py).
ai4science compute providers-add --id founder-1-subgpu \
  --wallet "$WALLET_FOUNDER_COMPUTE" --endpoint "$SUBGPU_INBOX" \
  --kind gpu --tier founder --price-usd-per-hour 1.50 --max-concurrent 2 \
  --label "Sub-GPU server (third-founder wallet)"

echo
echo "✓ Founder providers registered. Verify:"
echo "    ai4science llm providers   /   ai4science llm route"
echo "    ai4science compute providers"

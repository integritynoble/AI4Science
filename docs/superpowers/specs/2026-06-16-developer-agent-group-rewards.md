# Developer / Agent / Group Reward Mechanisms — pointer

The canonical design spec lives in the **pwm** repo (where the reward/emission plans
live), alongside the agent-mining plan and `emission.py`:

> `pwm-team/plan/PWM_DEVELOPER_AGENT_GROUP_REWARDS_2026-06-16.md`

## One-paragraph summary

Three reward tracks, each funded from a bucket that already exists in the
`emission.py` M_pool split:

- **Track 1 — Developer winner** (developer-winners bucket, 1/16, renamed from
  "weekly winners"): one developer crowned each period, scored
  `0.50·Agent + 0.30·A4S + 0.20·Web`; auto top-5 shortlist → director picks; fixed
  100 PWM prize.
- **Track 2 — Agent winner** (agent-improvement bucket, 3/4, **AI4Science agents**):
  a bespoke agent **L1→L4 ladder** (agent design → capabilities → eval → solutions)
  paid by usage-weighted emission; authoring a new plug-in = the L1 win
  (acceptance bounty + its own carved pool).
- **Track 3 — Group activity** (group bucket, 1/8): an admin hosts a competition,
  submits their own baseline, and recruits ≥3 joiners; 1st/2nd/3rd prizes where 1st
  must beat the admin (else the activity fails and nobody is paid); on success the
  admin earns the same as 1st place.

The original **principle L1→L4** artifact mining is the separate artifact-solo bucket
(1/16) and is unchanged.

See the canonical spec for scoring detail, anti-gaming, config knobs, conservation
rules, and acceptance criteria.

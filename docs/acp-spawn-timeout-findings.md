# ACP spawn/connect ~80s timeout — findings

Status: IN PROGRESS. This file is committed early and updated as evidence lands.

## Goal
Find the ~80s timeout in the OpenClaw ACP spawn/connect path (FILE, LINE, VALUE),
determine whether it is configurable on the spawn path, and remedy so a spawn
report distinguishes: (a) started+running, (b) started+finished, (c) never started.

## Search locations
1. acpx plugin: /home/tina1/.openclaw/npm/projects/openclaw-acpx-052d680d6d/node_modules/@openclaw/acpx/
   (dist/ + node_modules/)
2. OpenClaw gateway/session/spawn: /home/tina1/.nvm/versions/node/v24.19.0/lib/node_modules/openclaw
3. Our client (READ-ONLY): /home/tina1/pwm/AI4Science-engine/ai4science/harness/agents/sarsi/acp.py

## Findings
(pending — search underway)

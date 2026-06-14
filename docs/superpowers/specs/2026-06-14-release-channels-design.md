# AI4Science Release Channels — moved

This design has been merged into the combined PWM release & deploy mechanism,
which is the single source of truth (covers both the AI4Science CLI and the
physicsworldmodel.org website).

**Canonical doc:** `pwm` repo →
`pwm-team/plan/PWM_RELEASE_AND_DEPLOY_MECHANISM_2026-06-14.md`
(github.com/integritynoble/pwm, `pwm-team/plan/PWM_RELEASE_AND_DEPLOY_MECHANISM_2026-06-14.md`).

CLI specifics live in **Part A** of that doc (dev → rc → stable channels, PEP 440
version scheme, `cut-rc.sh`, channel-aware `install.sh`/`update`, the
`ci/rc/release` workflows, and the GitHub `production`-environment approval gate).

# The sarsi live gate

`sarsi_live_gate.py` runs the two `SARSI_LIVE_TEST=1` end-to-end tests against
a real engine, nightly. It exists because the suite ran ~4,600 tests green for
months while `sarsi-worker → sarsi-claude` had never once carried a prompt to a
model, and because the spawn guard added on 2026-08-27 means an ordinary run
can no longer start a real bridge at all. Nothing else exercises the transport.

The script lives here rather than in `~/pwm/ops` — where the box's other jobs
live untracked — so a rebuilt machine can restore it. `~/.config/systemd/user`
holds install artifacts, not a second copy to keep in sync: the units below are
the source.

Install:

    cp systemd/sarsi-live-gate.{service,timer} ~/.config/systemd/user/
    systemctl --user daemon-reload
    systemctl --user enable --now sarsi-live-gate.timer

Verify it can actually fail, not just pass:

    systemctl --user start sarsi-live-gate.service   # writes/clears the alert
    journalctl --user -u sarsi-live-gate.service -n 20

Outputs, both under `~/pwm-rescue/`:

| file | meaning |
|---|---|
| `ALERT-sarsi-live-gate.md` | both attempts failed, or a bridge outlived the run. Removed automatically when a later run passes. |
| `FLAKE-sarsi-live-gate.md` | failed once, passed on retry. Appended to, never cleared — a flake that is silently retried away is the same disease as a green suite hiding a dead transport. |

The unit carries no `Restart=` and no `SuccessExitStatus=`. Both re-label a
failure as healthy, and this box has already hidden two real outages behind
exactly those settings.

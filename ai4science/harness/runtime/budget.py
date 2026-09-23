"""A durable session budget: one cap, shared by a session and everything it
dispatches, that survives the process (ticket A03; the demo's controller,
brought into the runtime).

Every dispatch is an *action* with an id. It is reserved before it runs and
counts against the cap from that moment; it is reconciled afterwards as
delivered (with the cost that was actually metered) or released. A process
that dies between the two leaves the action `unknown` — still counted, never
re-dispatched under the same id, and listed for the owner to reconcile. That
is the whole point: after a kill, the ledger says what was in flight, and a
restart cannot double-spend it by forgetting.

SQLite with WAL and synchronous=FULL, so a reservation that returned has hit
the disk. Amounts are micro-PWM integers; floats never enter the arithmetic.
"""
from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable, Optional

MICRO = 1_000_000


def micro(value) -> int:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"amount must be a number, not {value!r}")
    if not d.is_finite() or d < 0:
        raise ValueError(f"amount must be finite and non-negative, not {value!r}")
    return int(d * MICRO)


def pwm(micro_value: int) -> float:
    return micro_value / MICRO


class BudgetError(RuntimeError):
    pass


class Budget:
    def __init__(self, path, cap_pwm=None):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path), isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS actions(
            id TEXT PRIMARY KEY, estimate INTEGER NOT NULL, actual INTEGER,
            status TEXT NOT NULL, note TEXT);
        """)
        stored = self.db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()
        if stored is None:
            if cap_pwm is None:
                raise BudgetError("a new budget needs a cap")
            self.db.execute("INSERT INTO meta VALUES('cap', ?)", (str(micro(cap_pwm)),))
        elif cap_pwm is not None and int(stored[0]) != micro(cap_pwm):
            raise BudgetError(
                f"this session's cap is {pwm(int(stored[0])):g} PWM; a restart "
                f"cannot change it to {cap_pwm} — the owner raises a cap, not a resume")

    # ── reading ────────────────────────────────────────────────────────
    @property
    def cap(self) -> int:
        return int(self.db.execute("SELECT value FROM meta WHERE key='cap'").fetchone()[0])

    def used(self) -> int:
        """Delivered actions at their actual cost, everything else in flight at
        its estimate; released actions count nothing."""
        return int(self.db.execute(
            "SELECT COALESCE(SUM(COALESCE(actual, estimate)), 0) FROM actions "
            "WHERE status != 'released'").fetchone()[0])

    def remaining(self) -> int:
        return self.cap - self.used()

    def unknown(self) -> list:
        return [r[0] for r in self.db.execute(
            "SELECT id FROM actions WHERE status='unknown' ORDER BY rowid")]

    def status(self, action_id: str) -> Optional[str]:
        row = self.db.execute("SELECT status FROM actions WHERE id=?", (action_id,)).fetchone()
        return row[0] if row else None

    def snapshot(self) -> dict:
        return {"cap_pwm": pwm(self.cap), "used_pwm": pwm(self.used()),
                "remaining_pwm": pwm(self.remaining()), "unknown": self.unknown(),
                "actions": [dict(id=r[0], estimate_pwm=pwm(r[1]),
                                 actual_pwm=None if r[2] is None else pwm(r[2]),
                                 status=r[3], note=r[4])
                            for r in self.db.execute(
                                "SELECT id, estimate, actual, status, note FROM actions "
                                "ORDER BY rowid")]}

    def next_id(self, prefix: str) -> str:
        n = self.db.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        return f"{prefix}:{n + 1}"

    # ── writing ────────────────────────────────────────────────────────
    def reserve(self, action_id: str, estimate_pwm, note: str = "") -> None:
        est = micro(estimate_pwm)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute("SELECT status FROM actions WHERE id=?",
                                    (action_id,)).fetchone()
            if prior is not None:
                raise BudgetError(
                    f"action {action_id!r} is already {prior[0]} — reconcile it, "
                    f"never dispatch it again under the same id")
            if self.used() + est > self.cap:
                raise BudgetError(
                    f"session cap reached: {pwm(self.used()):g} of {pwm(self.cap):g} PWM "
                    f"in use or unresolved, {pwm(est):g} more requested")
            self.db.execute("INSERT INTO actions(id, estimate, status, note) "
                            "VALUES(?, ?, 'unknown', ?)", (action_id, est, note))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def reconcile(self, action_id: str, *, delivered: bool, actual_pwm=None) -> None:
        target = "delivered" if delivered else "released"
        actual = None if actual_pwm is None else micro(actual_pwm)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT status, actual FROM actions WHERE id=?",
                                  (action_id,)).fetchone()
            if row is None:
                raise BudgetError(f"unknown action id {action_id!r}")
            if row[0] == target:
                if actual is not None and row[1] is not None and row[1] != actual:
                    raise BudgetError(f"action {action_id!r} was already reconciled "
                                      f"with a different actual cost")
                self.db.execute("COMMIT")
                return                      # idempotent replay
            if row[0] != "unknown":
                raise BudgetError(f"action {action_id!r} is {row[0]}; cannot mark it {target}")
            self.db.execute("UPDATE actions SET status=?, actual=? WHERE id=?",
                            (target, actual if delivered else None, action_id))
            self.db.execute("COMMIT")
        except Exception:
            self.db.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.db.close()


def open_for_session(sessions_dir: Path, session_id: str, cap_pwm=None) -> Optional[Budget]:
    """The session's budget: created when a cap is given, reopened when its
    file exists, None when neither — an uncapped session keeps no ledger."""
    path = Path(sessions_dir) / f"{session_id}.budget.sqlite"
    if cap_pwm is None and not path.exists():
        return None
    return Budget(path, cap_pwm)


def guard_session(session, budget: Budget, *, action_id: str, estimate_pwm=0,
                  cost_of: Optional[Callable[[object], float]] = None, note: str = ""):
    """Make a child session's run_turn a budgeted action.

    Reserved before the first token, reconciled as delivered with the metered
    cost after, left `unknown` if the turn raises or the process dies in
    between. The reservation refusal is raised BEFORE dispatch, so a refused
    child never runs at all."""
    real_run = session.run_turn
    real_meter = session.meter
    spent = {"pwm": 0.0}

    def _meter(u):
        if cost_of is not None:
            try:
                spent["pwm"] += float(cost_of(u) or 0.0)
            except Exception:
                pass
        real_meter(u)

    def run_turn(user_input, images=None):
        budget.reserve(action_id, estimate_pwm, note=note)
        result = real_run(user_input, images=images)
        budget.reconcile(action_id, delivered=True,
                         actual_pwm=spent["pwm"] if cost_of is not None else None)
        return result

    session.meter = _meter
    session.run_turn = run_turn
    session.budget_action_id = action_id
    return session

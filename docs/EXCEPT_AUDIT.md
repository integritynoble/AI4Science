# The blanket-except audit

165 `except Exception` / bare handlers across
`ai4science/harness/agents/sarsi/` and `.../machine/`, read with an AST pass
rather than by scrolling (`/tmp/audit.py`, reproduced below) so the
classification is over actual `try` bodies and not over what a grep line
happens to show.

## What was looked for

Not "is there a broad except" — most of these are correct. The question is
narrower:

> **Does the handler drop something the caller asked for, or hide a failure the
> caller caused?**

A broad except around `open()`, `json.loads()`, `subprocess.run()` or a
`Path` operation is usually right: the failure is a machine condition, the
handler reports it as unknown, and continuing is the honest answer. A broad
except around a call on an **injected object** is different — an
`AttributeError` or `TypeError` there means the caller passed the wrong thing,
and swallowing it turns a programming error into silent wrong behaviour.

## The shape of the 165

| | count |
|---|---|
| total blanket handlers | 165 |
| guarding a call on an injected object, and **not** a file/subprocess op | 25 |
| handler `pass` | 39 |
| handler returns or assigns a fallback | 80 |
| other | 46 |

Of the 25, most are already right, and they are right in one of three ways:

* **the handler reports** — `verifier.py:80` answers `UNVERIFIED`,
  `answering.py:114` escalates to the owner, `composer.py:67` returns a note,
  `digest.py:205` returns `ok=False`;
* **the handler re-raises after recording** — `transmit.py:104`/`375` raise
  `TransmitFailed`, `outward.py:181` records `failed` then re-raises,
  `undo.py:140` records `attempt-failed` and raises *"it is still published"*.
  That last one is the model the others were measured against;
* **the handler fails toward deny** — `vault.py:180` turns a broken prompt into
  no answer, `outward.py:142` turns a broken approval into a refusal. An error
  becoming a refusal is safe; an error becoming an approval would not be.

## What was fixed

| Where | What was dropped | Now |
|---|---|---|
| `sessions.py` `start_session` | `govern=True` — a hook that would not wire started the session **ungoverned**, with `ok: True` returned | refuses, names the cause, starts nothing |
| `session.py` `release` | `set_ceiling` — a failed raise still recorded the new ceiling, so the board showed A1 while the session ran at A0 | `CouldNotRelease`; the record keeps what the session has |
| `session.py` `release_session` | `.stop()` on a runtime that cannot stop — the record cleared and the terminal kept running (caught live) | falls back to the real runtime |
| `hook.py` tripwire | `_trust.record` and `_sup.update` — a forbidden command was blocked, and the **record that it was attempted** could vanish | the deny is untouched; the gap goes into the verdict's reason |
| `attention.py` `_from_pane`, `questions.py` | `pane.capture` failing became `None`/`""` — the value a **gone** pane gives — so one reported `dead-session` and the other retyped and claimed `NotDelivered` | `unreadable` and `NotConfirmed`: neither claims a fact nobody checked |
| `gateway.py` `_dispatch` | `send_message` — a reply the agent gave and the owner never received, indistinguishable in the log from one that arrived | the send happens first; the log records `delivered`, and the ledger carries the reason |

The first three follow one rule: **honoured or refused, never dropped.** The
fourth cannot, and the reason is worth stating — the hook is a subprocess Claude
Code depends on, so raising would leave it with *no verdict at all*, which is a
worse failure than an unrecorded one. There the gap is surfaced instead.

## What was deliberately left

* **~140 file, JSON, subprocess and path guards.** Failing open is the designed
  behaviour and the callers read the fallback as "unknown".
* **`attention.py:312`** — already honest: it says *"whether it is waiting,
  working or gone is unknown"* rather than claiming any of them.
* **`agent.py:54`, `session.py:351`** — a dropped audit record. Real, and
  smaller than the four above: nothing decides on it.

## Reproducing it

```
python3 /tmp/audit.py      # AST pass; prints the 25 and the shape of the 165
```

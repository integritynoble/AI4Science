# How to Earn PWM by Giving Feedback

You earn PWM by helping improve the AI4Science agents. It takes one command.

> Developer reference (how the server checks & rewards feedback): see
> [`AGENT_POOL_API.md`](AGENT_POOL_API.md) §1b and the pwm_nonprofit doc
> `platform/docs/FEEDBACK_REWARD.md`.

## 1. Use an agent

Start a chat and actually use it for a bit (e.g. `ai4science chat`, or pick a
mode like Claude / research / paper). Feedback is tied to the **agent you're
currently using**.

## 2. Send feedback with `/feedback`

In the chat, type:

```
/feedback <what worked, what didn't, and how to make it better>
```

Example:

```
/feedback The CASSI forward-check was great, but the glob tool kept scanning the
whole machine. Default it to the project and it'd be perfect.
```

## 3. You get PWM based on **quality** — no login required

- **No wallet needed.** If you're not logged in, a local wallet is created for
  you automatically, so feedback always submits and can still earn PWM.
- **Paid by usefulness.** An automated judge scores each piece of feedback
  `0–1`. Specific, actionable feedback earns PWM; one-word or empty feedback
  earns nothing.
- Your reward is credited from the agent's reward pool. You'll see a result line
  like `[pwm] feedback for <agent>: accepted (+N PWM)`.

## What makes feedback earn the most

- **Be specific** — name the tool, mode, or step that helped or broke.
- **Say how to improve it** — a concrete suggestion beats "it was bad."
- **One real point per message** — duplicates and spam are filtered out (and
  there's a small daily cap per agent).
- **Earlier is worth more** — early feedback on an agent refills the most.

## Tips

- `/feedback` with no text shows the usage hint.
- It works the same in every mode, including real Claude mode (it's handled
  locally — it never goes to the model).

## Possible result statuses

| You see | Meaning |
| --- | --- |
| `accepted (+N PWM)` | Good feedback — PWM credited. |
| `low_quality` | Too short / not actionable — refine and resend. |
| `duplicate` | Same as a recent one — say something new. |
| `rate_limited` | Hit the daily cap for this agent — try again tomorrow. |
| `program_full` | Early-adopter reward slots are full for now. |

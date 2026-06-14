# Become a Compute Provider (earn PWM)

Anyone can rent out their **GPU** or **high-performance CPU** to AI4Science
users and earn PWM. When a user runs a job on your machine, they pay you in PWM;
the Physics Judge re-verifies every result, so you're paid for *verified* work.

> Prices are native **PWM/hour** (the unit users hold). Every charge is split
> **90% to you, 10% to the PWM pool**.

## 1. Register your machine

```bash
ai4science compute join \
  --wallet 0xYourEthAddress \
  --kind gpu \                 # gpu | cpu
  --price-pwm-per-hour 0.30 \  # your rate (default: 0.30 gpu / 0.04 cpu)
  --endpoint /path/to/shared/inbox
```

- `--wallet` — the 0x address your PWM earnings accrue to.
- `--price-pwm-per-hour` — what you charge. Users are shown this before they
  dispatch; cheaper providers are selected first.
- `--endpoint` — a directory the dispatcher and your machine both see (a shared
  folder, or a git-synced dir for cross-machine).
- One job at a time by default (`--max-concurrent 1`). Raise it **only** if your
  box can truly run jobs in parallel (e.g. multiple GPUs).

This adds you to the registry as an **open-tier** provider. Check it:

```bash
ai4science compute providers      # lists id, kind, PWM/hr, wallet, eligibility
```

## 2. Become eligible (stake)

Providers must be stake-eligible to be selected (anti-spam / skin-in-the-game):

```bash
ai4science stake add
```

## 3. Run the poller (serve jobs)

On the machine with the GPU/CPU:

```bash
ai4science compute serve --provider <your-id> --allow-exec
# add --git-sync if the inbox is a git-shared dir on another machine
# add --once for a cron-friendly single pass
```

- `--allow-exec` is **required** to actually run dispatched solver code — only
  use it on a host where you trust the dispatcher. Without it the poller acks
  jobs but refuses to execute (safety gate).
- The poller watches your inbox, runs each job, writes results + a certificate
  back, and releases the lease slot.

## 4. How you earn

1. A user (in any agent) picks your provider and dispatches a job:
   `compute_dispatch(provider="<your-id>", run_command="…", confirm=true)`.
2. Your poller runs it and returns a result.
3. The **Physics Judge** re-verifies. On a verified pass, the user is charged
   `your PWM/hr × actual runtime`, and **90%** lands in your wallet (10% → pool).
4. A bad/unverified result earns nothing — you're paid for real, checked work.

Track earnings:

```bash
ai4science compute spend          # priced PWM earned per wallet
ai4science compute credits        # verified-job credits
```

## Notes

- **Local compute is free** — running on your own machine via the agent's bash
  tool costs no PWM. You only pay when you dispatch to *someone else's* provider.
- **Founder servers** (`founder-gpu` 0.30 PWM/hr, `founder-cpu` 0.04 PWM/hr) are
  seeded defaults so every agent has compute available out of the box; both
  serve one job at a time.
- Set a different rate later by re-running `join` (same id replaces) or
  `ai4science compute providers-add --id <id> … --price-pwm-per-hour <rate>`.

# Sub-GPU Poller — Windows Setup Guide

How to turn your **Windows + CUDA + PyTorch** box into an AI4Science
compute provider that runs dispatched solvers and earns judge-verified
credits to your wallet.

This guide is for the Phase 0 setup (founder's own GPU). See
[`COMPUTE_PROVIDERS_DESIGN.md`](COMPUTE_PROVIDERS_DESIGN.md) for the full
architecture and the trust model.

---

## What you're setting up

```
 cloud agent / your laptop                    your Windows GPU box
 ─────────────────────────                    ────────────────────
 ai4science compute dispatch  ──┐          ┌── ai4science compute serve --allow-exec
                                │          │      (this guide)
                            ┌───▼──────────▼───┐
                            │  shared inbox dir │   job_<id>.request.json
                            │  (synced folder)  │   job_<id>.ack.json
                            └───┬──────────┬───┘   job_<id>.result.json
                                │          │
 ai4science compute verify  ◄───┘          └──► poller runs your solver on the GPU
   (judge → credit to wallet)
```

The two sides talk through a **shared directory**. The GPU box polls it,
runs the solver, writes results back. The agent verifies with the
deterministic Physics Judge and credits your wallet only if it passes.

---

## Prerequisites

On the Windows box you should already have (per your `SUBGPU_STATUS.md`):

- Python 3.10+ (you have 3.12)
- PyTorch 2.x + CUDA (you have 2.6 + CUDA 12.7)
- `git` (for pulling the AI4Science repo and/or syncing the inbox)

Check from **PowerShell**:

```powershell
python --version
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

You should see `True` and your GPU's name.

---

## Step 1 — Install AI4Science on the Windows box

```powershell
cd C:\pwm
git clone https://github.com/integritynoble/AI4Science.git
cd AI4Science

python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -e .
ai4science --version
ai4science compute --help
```

> If `Activate.ps1` is blocked, run once:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

Your GPU solvers (PnP-HDNet, DAUHST-9stg, RDLUF-MixS2, ...) bring their
own deps — install those into the same venv as usual.

---

## Step 2 — Bind your wallet (register this box as a provider)

This records that verified work from this box credits your wallet:

```powershell
ai4science compute providers-add `
  --id founder-1-subgpu `
  --wallet 0xf1Fa5803daAAaFf89932592ad54F4e7F5e3f7DEE `
  --endpoint C:\pwm\compute_jobs `
  --label "Director (Yang) sub-GPU - Ledger Nano S Plus" `
  --tier founder

ai4science compute providers
```

- `--endpoint` is the **shared inbox** path on this box (set up in Step 3).
- The registry is stored at `%USERPROFILE%\.config\ai4science\compute_providers.json`.
- The wallet is the address rewards accrue to — your Ledger Nano S Plus
  address. The CLI never touches keys; it only records the address.

---

## Step 3 — Set up the shared inbox

The agent and the GPU box must see the **same** `compute_jobs/` directory.
Pick whichever matches your topology:

### Option A — Same machine
If you dispatch and serve on the same Windows box, just use a local path
(`C:\pwm\compute_jobs`). Nothing else to do.

### Option B — Git-synced inbox (matches your existing baseline_runs flow)
You already coordinate the sub-GPU via the git inbox
(`pwm-team/coordination/agent-coord/inbox/baseline_runs/`). Reuse that:

- Point `--endpoint` at a `compute_jobs/` folder inside the repo working tree.
- The dispatcher commits+pushes the request; the GPU box `git pull`s,
  runs, commits+pushes the result; the dispatcher pulls to verify.
- Simple, auditable, no extra infra. Slightly higher latency (a pull/push
  per step). Good for batch work.

### Option C — Cloud-synced folder (lowest latency)
Use a synced folder both machines mount: Syncthing, Dropbox, OneDrive,
`rclone mount`, or an SMB network share. Point `--endpoint` at the local
mount path on each side. Near-real-time; best for interactive dispatch.

> Whatever you choose, the path in `--endpoint` is the **local** path on
> the box where the poller runs.

---

## Step 4 — Make the workspace + data reachable

A job request carries the **workspace path** (where `data/` and the solver
`code/` live). The poller runs the solver with that workspace as its
working directory, so the GPU box must be able to reach it.

Two common setups:

1. **Data already on the GPU box** (your current model): the dataset is
   local (`gs://pwm-benchmark-datasets/...` downloaded to the box). The
   dispatched workspace should resolve to that local copy. Easiest when
   dispatch and serve run on the same box or a shared drive.
2. **Synced workspace**: ship the workspace (code + data) through the same
   sync mechanism as the inbox (Option B/C above).

> Phase 0 assumes the workspace path is reachable on the GPU box (same
> machine or shared/synced filesystem). True "package the workspace and
> send it" remote execution is a later phase.

---

## Step 5 — Run the poller

```powershell
.\.venv\Scripts\Activate.ps1
ai4science compute serve --provider founder-1-subgpu --allow-exec
```

You'll see:

```
ai4science compute serve - provider founder-1-subgpu
  wallet:  0xf1Fa5803daAAaFf89932592ad54F4e7F5e3f7DEE
  inbox:   C:\pwm\compute_jobs
  exec:    enabled
  mode:    polling every 5s (Ctrl-C to stop)

> job a1b2c3d4e5f6 picked up
  + job a1b2c3d4e5f6 ran -> cert 0xb3166a8997dd...
```

Flags:

| Flag | Meaning |
|---|---|
| `--allow-exec` | **Required** to actually run dispatched solver code. Without it the poller acks jobs but won't execute. |
| `--once` | Process pending jobs and exit (good for Task Scheduler / cron). |
| `--interval N` | Poll every N seconds (default 5). |

> **`--allow-exec` runs dispatched commands on your machine.** In Phase 0
> the dispatcher is you (the founder), so it's trusted. Never point this at
> an inbox an untrusted party can write to without sandboxing.

---

## Step 6 — Run it persistently

### Option A — Task Scheduler (poll-once on a timer)

Create a `.bat` launcher `C:\pwm\run_poller.bat`:

```bat
@echo off
cd /d C:\pwm\AI4Science
call .venv\Scripts\activate.bat
ai4science compute serve --provider founder-1-subgpu --once --allow-exec
```

Then register a scheduled task that runs it every 2 minutes:

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\pwm\run_poller.bat"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
             -RepetitionInterval (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName "ai4science-subgpu-poller" `
  -Action $action -Trigger $trigger -RunLevel Highest
```

### Option B — Always-on service (NSSM)

For a continuously-polling service, use [NSSM](https://nssm.cc/):

```powershell
nssm install ai4science-poller "C:\pwm\AI4Science\.venv\Scripts\ai4science.exe" `
  "compute serve --provider founder-1-subgpu --allow-exec"
nssm set ai4science-poller AppDirectory "C:\pwm\AI4Science"
nssm start ai4science-poller
```

Logs: `nssm set ai4science-poller AppStdout C:\pwm\poller.log`.

---

## Step 7 — Verify it works (test job)

From the **agent side** (same box is fine for the test):

```powershell
cd C:\pwm\AI4Science
ai4science init test-demo
cd test-demo

# generate data + reconstruction so the judge has something to check
python code\generate_data.py --workspace .
python code\run_solver.py --workspace .

# dispatch a job to your provider
ai4science compute dispatch --provider founder-1-subgpu `
  --benchmark L3-003-001-001-T1 --run-command "python code/run_solver.py"
```

If the poller is running, within a few seconds you'll see it pick the job
up. Then verify and check credits:

```powershell
ai4science compute status <job_id> --provider founder-1-subgpu
ai4science compute verify <job_id> --provider founder-1-subgpu
ai4science compute credits
```

A judge **pass** adds one verified-job credit to your wallet in
`reports/compute_attributions.jsonl`.

---

## Windows gotchas

| Issue | Fix |
|---|---|
| `run_command` with backslashes gets mangled | Use **forward slashes** in run commands: `python code/run_solver.py` (Python accepts `/` on Windows). |
| `Activate.ps1` blocked | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Poller says **"not run"** | The `run_command` interpreter isn't on PATH. Use the full venv python, e.g. `--run-command "C:/pwm/AI4Science/.venv/Scripts/python.exe code/run_solver.py"`. |
| Poller says **"workspace not reachable"** | The job's workspace path doesn't exist on this box. Use a shared/synced workspace (Step 4). |
| Git line endings flip JSON files | `git config core.autocrlf false` in the inbox repo so JSON stays LF. |
| GPU not used | Confirm your solver actually selects CUDA; the poller just runs your command — device selection is your solver's job. |

---

## Security checklist

- [ ] `--allow-exec` is only used on a host where you trust the dispatcher.
- [ ] The inbox is not writable by untrusted parties (Phase 0 = founder only).
- [ ] Your wallet **private key never goes on this box** — only the public
      address is in the registry. The CLI moves no tokens.
- [ ] Solvers run as your user; for untrusted solver code later, run the
      poller inside a container or a restricted Windows account.

---

## What the poller does (recap)

1. Watches `<endpoint>` for `job_*.request.json` with no ack/result.
2. Writes `job_<id>.ack.json` (accepted, started).
3. Runs the job's `run_command` with `cwd` = the job's workspace (GPU work).
4. Computes a content-addressed `certificate_hash` over the reconstruction.
5. Writes `job_<id>.result.json` (manifest + your wallet + metrics).

The agent then runs `ai4science compute verify`, which re-checks the result
with the deterministic Physics Judge and credits your wallet **only if it
passes**. Fake or broken results earn nothing — that's what makes the
whole thing safe.

# Compute HTTP Relay — design (arbitrary-user GPU dispatch)

**Date:** 2026-06-15 · **Status:** design (approved decisions) → implementation
**Replaces:** git-as-transport (see `COMPUTE_MECHANISM.md` §3A) for anyone without
the `pwm` repo. The handshake, Physics-Judge verification, and 90/10 PWM
accounting are **unchanged** — only the transport link changes.

## Problem

The git-synced inbox requires the `pwm` repo + push access (founder-only) and
permanently bloats the repo: every request/ack/result/reconstruction/weight is
committed into git history forever (GitHub 100 MB/file + repo-size limits). It
cannot serve an arbitrary user.

## Decisions (locked)

1. **Strangler migration.** Build HTTP as the new default transport; keep git
   behind a flag during bring-up; delete the git transport in a follow-up once
   HTTP is verified in production. No window without a working path.
2. **Two planes.** HTTP carries only small JSON (control plane); large artifacts
   (weights, datasets, reconstructions) move via **GCS presigned URLs** (data
   plane) — reusing the existing `gs://` `dataset_ref` pattern. The relay never
   proxies big bytes.

## Architecture

```
USER (any machine, PWM login, no repo)        physicsworldmodel.org (relay)         GPU BOX (provider)
  ai4science compute dispatch                    POST /compute/jobs                    ai4science compute serve --http
    → mint presigned PUT, upload workspace ──────► (auth + PWM preauth)                  loop:
      tarball to GCS                               store job (state=requested)            GET /compute/claim ───► lease+ack (atomic)
    → POST job {refs, run_command, ...}            ◄──────────────────────────           download workspace tarball (presigned GET)
  ai4science compute result (poll)                 GET /compute/jobs/{id}                 run solver (--allow-exec, bounded)
    ◄── result JSON + reconstruction ref           ◄── result+ref                         upload reconstruction (presigned PUT)
    → download reconstruction (presigned GET)                                             POST /compute/jobs/{id}/result
    → local Physics Judge re-verify                POST .../heartbeat (each poll)          (judge may also run server-side)
                                                   charge PWM 90/10 on verified pass
```

### Control plane — REST (on `pwm_nonprofit`, `routers/compute.py`)

All authenticated with the user's PWM token (same bearer as the LLM proxy).

| Method · path | Caller | Body / returns |
|---|---|---|
| `POST /api/v1/compute/uploads` | user | `{kind, filename, size}` → presigned **PUT** URL + object key (workspace tarball, weights) |
| `POST /api/v1/compute/jobs` | user | `{provider_id, run_command, workspace_ref, dataset_ref, max_runtime_s}` → `{job_id, state, pwm_preauth}`. PWM-gated: rejects if balance < est cost. |
| `GET /api/v1/compute/jobs/{id}` | user | job state + (when done) `result` + `reconstruction_ref` (presigned GET) |
| `GET /api/v1/compute/claim?provider_id=` | provider | atomically lease the oldest `requested` job for that provider → job + presigned GET for the workspace; writes ack. 204 if none. |
| `POST /api/v1/compute/jobs/{id}/result` | provider | `{metrics, solver_*, wall_clock_s, reconstruction_ref}` → marks `completed`, triggers verify + charge |
| `POST /api/v1/compute/providers/{id}/heartbeat` | provider | liveness stamp (replaces the git heartbeat file) |
| `GET /api/v1/compute/providers` | anyone | provider list + `● online/○ offline` from last heartbeat |

State machine unchanged: `requested → acked(leased) → completed`. The server is
the single source of truth (DB), so the two machines still never talk directly.

### Data plane — authenticated GCS proxy

> **Pivot (2026-06-15):** signed URLs are **disabled** in this GCP project
> (`gcs_signer.py`: IAM signing off). So the data plane is an **authenticated
> streaming proxy** through the relay, not direct presigned URLs: artifacts are
> uploaded/downloaded via `POST/GET /api/v1/compute/blobs` (auth = user token OR
> provider key) and stored in GCS (in-memory fallback for dev). A blob key is an
> unguessable random id (capability model). Bytes still never touch git, and GCS
> stays the ephemeral store (bucket lifecycle TTL). If IAM signing is enabled
> later, swap the proxy for presigned URLs behind the same `upload_blob/download_blob`
> seam. The original presigned plan is kept below for reference.

### (reference) Data plane — GCS presigned URLs

- **Upload:** client/provider request a presigned PUT, transfer the artifact
  straight to the bucket. Server stores only the **object key** on the job row.
- **Download:** server returns a short-TTL presigned GET; the other side pulls
  directly from GCS. The relay never streams large bytes.
- **Scope/TTL:** presigned URLs are per-object, short-lived (e.g. 15 min),
  method-restricted. Bucket lifecycle rule auto-deletes job objects after N days
  (solves git's "forever" problem — artifacts are ephemeral).
- **Small jobs:** workspace tarballs under a threshold (e.g. 1 MB) MAY be inlined
  base64 in the job body to save a round-trip; anything larger MUST use GCS.

### Auth + PWM (reuse existing)

- User auth = the PWM login bearer (the LLM-proxy path already does auth + charge).
- `POST /jobs` **pre-authorizes** `est_pwm = rate × max_runtime_s/3600`
  (reject if insufficient); actual charge on the verified result is the existing
  `billing.charge_compute` 90/10 split. Failed/unverified job → no charge.
- Providers authenticate to `claim`/`result` with a provider key bound to their
  earning wallet.

## Client side (`ai4science/compute`)

A `transport` abstraction selects the link; the dispatch/result commands and the
`compute_*` tools call the transport, not git directly.

- `transport.select(provider)` → `HttpTransport` when `PWM_BASE`/login is present
  and the provider is remote (default), else `GitTransport` (legacy, flag
  `AI4SCIENCE_COMPUTE_TRANSPORT=git`) when the user has the repo.
- `HttpTransport.dispatch(job, workspace)` — tar the workspace, presign+upload,
  POST the job. `.poll(job_id)` — GET; on done, download the reconstruction.
- `GitTransport` = today's behavior, kept behind the flag during the strangler.

## Provider side

`compute serve --http --provider <id>` loop: `GET /claim` (lease+ack) → download
workspace → run solver (`--allow-exec`, `max_runtime_s`) → upload reconstruction
→ `POST /result` → `POST /heartbeat`. Mirrors the git serve loop; no repo needed.

## Verification & accounting — unchanged

The deterministic Physics Judge (S1–S4, no LLM) recomputes from the
reconstruction. `pass → credit=1 → charge`. Can run server-side on `POST /result`
(authoritative) and/or client-side after download (independent re-verify).

## Security notes

- `--allow-exec` still required on the box; Phase-0 trust = founder providers.
  Community providers must sandbox (existing `COMPUTE_PROVIDERS_DESIGN.md §7`).
- Presigned URLs: per-object, short TTL, least-privilege; never a bucket-wide token.
- The relay validates `run_command`/refs belong to the authenticated job; one
  user can't claim another's objects.

## Phasing (strangler)

- **P1 — control plane:** `routers/compute.py` (jobs/claim/result/heartbeat,
  auth + PWM preauth) with **inline small payloads** (no GCS yet) + DB model.
  Client `HttpTransport` + `transport.select`. Provider `serve --http`. E2E test
  on a tiny job. *(Proves the link without cloud deps.)*
- **P2 — data plane:** GCS presigned upload/download for large artifacts;
  bucket lifecycle TTL. Move weights/datasets/reconstructions off inline.
- **P3 — make HTTP the default**, git behind `AI4SCIENCE_COMPUTE_TRANSPORT=git`.
  Verify a real MST-L job from a repo-less machine end-to-end in production.
- **P4 — delete the git transport** (`--git-sync`, the inbox serve path, the
  in-tree `compute_jobs/` inbox) once P3 is proven. Update `COMPUTE_MECHANISM.md`.

## Out of scope (now)

Multi-region buckets; provider auto-scaling; streaming logs; non-GCS object
stores (S3 adapter is a later swap behind the same presign interface).

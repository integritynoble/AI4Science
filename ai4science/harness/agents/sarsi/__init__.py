"""sarsi — the worker plane above `sarsi-claude`, on one machine.

Design: `singularity/docs/specs/2026-08-02-sarsi-worker-one-machine-design.md`.

The invariant everything here rests on: **the agent you talk to does not
execute.** The machine agent routes, plans and answers; only a worker touches
`sarsi-claude`; and only the vault holds a secret.
"""

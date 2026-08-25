# The harness ladder, and the first measured scaling curve

**Status: HG0–HG3 built and measured, 2026-08-25.**

The Unified Intelligence framework (v1.3) defines the Harness Scaling Curve
`HSC_m(k) = HLIS(m, HG_k)` and says it should remain a primary result because it
exposes saturation and non-monotonic behaviour. It is a specification — the
ladder is described per generation and nothing instantiates it. This builds the
first four rungs and runs one frozen model across them.

```
python -m ai4science.harness.agents.delegation.run_ladder --seeds 0-1
```

## The ladder

Each rung is a **strict superset** of the one below. Without that, a difference
between rungs is attributable to nothing — and a test enforces it.

| rung | adds | attempts | acceptance | reversible | routes |
|---|---|---|---|---|---|
| `HG0` | the model, bounded tools, an evidence log | 1 | **none** | no | no |
| `HG1` | persistent state; a criterion registered before the work exists; acceptance in a separate process | 1 | yes | no | no |
| `HG2` | snapshot before the first mutation; restore; retry with the failed check named | 3 | yes | yes | no |
| `HG3` | failure classification; an evidence-based competence model; routing | 4 | yes | yes | yes |

**HG0 has no acceptance step on purpose.** A harness that cannot accept cannot
report success either, so its score comes from the benchmark's verifier outside.
That makes it the honest baseline: it is the configuration a contemporary
leaderboard measures.

## The curve

One model, six classes, two seeds, 48 episodes, **only the harness changing**:

```
rung   A_DI   HLIS_DI   false-done   held-back   attempts
HG0    0.933    93.3         2           0          12
HG1    0.933    93.3         0           2          12
HG2    0.967    96.7         0           1          15
HG3    0.967    96.7         0           1          14

HSC: 93.3 → 93.3 → 96.7 → 96.7
HIL-Ceiling 96.7 | HIL-AUC 95.0 | Harness Gain 3.3
```

### The first segment is the finding

HG1 adds persistent state, a pre-registered criterion, and acceptance by a
separate process. **A_DI does not move** — not close, identical — while wrong
work handed back as finished goes 2/12 → 0/12 and two results are held back
instead. Opposite outcomes for anyone delegating; the same number.

The cause is structural. `A_DI` is the weighted mean of `S_A(T,H) = P(success)`.
**Acceptance does not change the probability of success. It changes what is
reported as success.** So a statistic defined on `P(success)` is exactly
invariant to the whole acceptance mechanism — and the rung it cannot see is the
one on which every claim above it depends.

It is worse than blind: a harness that accepts everything scores at least as well
as one that declines wrong work, so the gradient points away from strictness.

**The repair**, in the v0.2 library:

```
S_net(T,H) = P(verifier pass) − ρ · P(false completion)
```

On the same 48 episodes: **86.7 → 93.3 → 96.7 → 96.7**. First-rung rise 0.0 →
+6.7; Harness Gain 3.3 → 10.0. `score_hlis.py --gross` reproduces the v1.3
number, so the difference is auditable.

### The other two segments, reported honestly

**HG1 → HG2 is +3.4** and is the first rung whose mechanism requires the model to
convert a detected failure into a correction.

**HG2 → HG3 is flat because routing had one executor to choose between.** The
mechanism was present and inert. That is a defect in this instantiation, not
saturation, and it should not be read as a fact about the model.

**The curve is nearly saturated at HG0** (93.3), leaving 6.7 points for four
rungs. A model already solving five of six classes single-shot is a weak test of
the ladder. The informative experiment uses a model with a lower HG0.

## A bug the run found

The run crashed partway. When the model failed twice on a class, the router
classified it `CAPABILITY`, excluded it, and then chose the **criteria provider**
as the only remaining executor — which refuses to execute. A prohibitive cost was
not enough to keep a non-executor out of the pool once every real executor had
been excluded. Non-executors are now filtered from the routing pool outright, and
an executor that cannot run ends the episode with a reason rather than a
traceback.

## Files

```
ai4science/harness/agents/delegation/
├── ladder.py       the rungs, A_DI, the frontier, and the curve summaries
└── run_ladder.py   runs one frozen model across the ladder
tests/dli/test_level_agents.py   ladder tests, including the blindness as arithmetic
```

The paper is `The_Curve_Cannot_See_Its_First_Rung.md` in the
`sarsi-intelligence-level` corpus; the bindings and the repaired run-log schema
are in `dataset/HIL_Benchmark_Library_v0_2/` there.

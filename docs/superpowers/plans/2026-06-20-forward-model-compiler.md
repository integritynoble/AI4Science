# Forward-Model Compiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a forward-model compiler that turns a structured description of an imaging forward model (a pipeline of primitive ops) into an executable, differentiable `pwm_core` `PhysicsOperator` with automatic validation (adjoint dot-product, dimensions, linearity, conditioning), exposed as PWM-metered agent tools for the computational-imaging and research agents.

**Architecture:** A new pure-numpy library `pwm_core.forward_compiler` defines a serializable `ForwardModel` IR (an ordered list of `Stage`s), a registry of differentiable `Primitive` ops (each with `forward`/`adjoint`/`out_shape`/`is_linear`), a `compile()` that composes them into a `CompiledOperator(BaseOperator)` (forward = primitives left→right, adjoint = primitive adjoints right→left, inheriting `BaseOperator.check_adjoint` for free), an `as_torch()` autograd wrapper for differentiability of linear models, validators that produce a `ForwardModelReport`, and a `bridge` from existing digital-twin spec fields. On top, `ai4science/harness/forward_model_tools.py` adds `fm_primitives`/`fm_compile`/`fm_validate`/`fm_simulate` tools wired in as a new `"forward-model"` capability bundle. The agent supplies the structured model (NL→structure is the agent's job via tool docs); the compiler is deterministic and fully unit-testable.

**Tech Stack:** Python 3.12, numpy (mandatory), torch 2.10 (optional, for `as_torch`), pwm_core (`BaseOperator`, `core.registry`, `mismatch.subpixel`, `physics.spectral.dispersion_models`), AI4Science harness (`Tool` dataclass, capability bundles), pytest.

---

## File Structure

**New library — `packages/pwm_core/pwm_core/forward_compiler/`:**
- `__init__.py` — public exports (`ForwardModel`, `Stage`, `compile_model`, `PRIMITIVES`, `register_primitive`, `validate_forward_model`, `ForwardModelReport`, `from_modality`).
- `ir.py` — `Stage` + `ForwardModel` dataclasses (serializable IR).
- `primitives.py` — `Primitive` dataclass, `PRIMITIVES` registry, `register_primitive`/`get_primitive`, and the built-in primitives (`scale`, `mask_multiply`, `band_shift`, `band_sum`, `square_magnitude`, `gaussian_noise`).
- `compiler.py` — `CompiledOperator(BaseOperator)`, `compile_model()`, `as_torch()` helper.
- `validate.py` — `validate_dimensions`, `classify_linearity`, `probe_conditioning`, `ForwardModelReport`, `validate_forward_model`.
- `bridge.py` — `from_modality()` (modality template → `ForwardModel`) + `from_spec_fields()`.

**New tests — `packages/pwm_core/tests/`:**
- `test_fc_ir.py`, `test_fc_primitives.py`, `test_fc_compiler.py`, `test_fc_torch.py`, `test_fc_validate.py`, `test_fc_bridge.py`, `test_fc_golden_cassi.py`.

**New AI4Science layer:**
- Create: `AI4Science/ai4science/harness/forward_model_tools.py`
- Modify: `AI4Science/ai4science/harness/agents/capabilities.py` (add `"forward-model"` bundle)
- Modify: `AI4Science/ai4science/harness/agents/specs/computational_imaging.py` (add capability)
- Modify: `AI4Science/ai4science/harness/agents/specs/research.py` (add capability)
- Test: `AI4Science/tests/test_forward_model_tools.py`

**Conventions:**
- pwm_core tests run from `packages/pwm_core/`: `cd packages/pwm_core && python3 -m pytest tests/<file> -v`. (`python` is not on PATH in this environment — always use `python3`.)
- AI4Science tests run from `AI4Science/`: `cd AI4Science && python3 -m pytest tests/<file> -v`.
- The IR holds numpy arrays directly in `Stage.params` (in-memory). JSON persistence of array params is a *tool-layer* concern (`{"$ref": "file.npy"}`), handled in `forward_model_tools.py` — pwm_core stays array-native.

---

## Task 1: ForwardModel + Stage IR

**Files:**
- Create: `packages/pwm_core/pwm_core/forward_compiler/__init__.py`
- Create: `packages/pwm_core/pwm_core/forward_compiler/ir.py`
- Test: `packages/pwm_core/tests/test_fc_ir.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_ir.py
"""IR round-trip + validation for the forward-model compiler."""
from __future__ import annotations

import numpy as np
import pytest

from pwm_core.forward_compiler.ir import ForwardModel, Stage


def test_stage_roundtrip_plain_params():
    s = Stage(op="scale", params={"c": 2.0})
    assert Stage.from_dict(s.to_dict()) == s


def test_forward_model_roundtrip():
    m = ForwardModel(
        name="demo",
        x_shape=(4, 4, 3),
        stages=[Stage(op="scale", params={"c": 2.0}),
                Stage(op="band_sum", params={})],
        dtype="float32",
        metadata={"modality": "demo"},
    )
    m2 = ForwardModel.from_dict(m.to_dict())
    assert m2 == m
    assert m2.x_shape == (4, 4, 3)
    assert [st.op for st in m2.stages] == ["scale", "band_sum"]


def test_forward_model_requires_name_and_stages():
    with pytest.raises(ValueError):
        ForwardModel(name="", x_shape=(2,), stages=[Stage(op="scale", params={})])
    with pytest.raises(ValueError):
        ForwardModel(name="x", x_shape=(2,), stages=[])


def test_array_param_survives_in_memory():
    mask = np.ones((4, 4), dtype=np.float32)
    s = Stage(op="mask_multiply", params={"mask": mask})
    # to_dict keeps the array object (persistence is a tool-layer concern)
    assert s.to_dict()["params"]["mask"] is mask
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_ir.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pwm_core.forward_compiler'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/pwm_core/pwm_core/forward_compiler/__init__.py
"""pwm_core.forward_compiler

Forward-model compiler: a structured description of an imaging forward model
(an ordered pipeline of primitive ops) compiled into an executable, validated
pwm_core PhysicsOperator.
"""
from __future__ import annotations

from pwm_core.forward_compiler.ir import ForwardModel, Stage

__all__ = ["ForwardModel", "Stage"]
```

```python
# packages/pwm_core/pwm_core/forward_compiler/ir.py
"""Forward-model intermediate representation (IR).

A ForwardModel is an ordered list of Stages; each Stage names a primitive op
(see primitives.py) and carries its params. Params may hold numpy arrays in
memory (e.g. a coded-aperture mask); JSON persistence of arrays is handled by
the tool layer, not here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class Stage:
    op: str
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"op": self.op, "params": dict(self.params)}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Stage":
        return cls(op=d["op"], params=dict(d.get("params", {})))


@dataclass
class ForwardModel:
    name: str
    x_shape: Tuple[int, ...]
    stages: List[Stage]
    dtype: str = "float32"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ForwardModel.name must be non-empty")
        if not self.stages:
            raise ValueError("ForwardModel.stages must be non-empty")
        self.x_shape = tuple(int(d) for d in self.x_shape)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "x_shape": list(self.x_shape),
            "stages": [s.to_dict() for s in self.stages],
            "dtype": self.dtype,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ForwardModel":
        return cls(
            name=d["name"],
            x_shape=tuple(d["x_shape"]),
            stages=[Stage.from_dict(s) for s in d["stages"]],
            dtype=d.get("dtype", "float32"),
            metadata=dict(d.get("metadata", {})),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_ir.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/__init__.py packages/pwm_core/pwm_core/forward_compiler/ir.py packages/pwm_core/tests/test_fc_ir.py
git commit -m "feat(forward-compiler): ForwardModel + Stage IR"
```

---

## Task 2: Primitive registry + linear primitives

**Files:**
- Create: `packages/pwm_core/pwm_core/forward_compiler/primitives.py`
- Test: `packages/pwm_core/tests/test_fc_primitives.py`

Each primitive declares `forward(x, **params)`, `adjoint(y, **params)` (None if nonlinear), `out_shape(in_shape, **params)`, and `is_linear`. Linear primitives are validated with the inner-product adjoint test `<Ax, y> == <x, A^T y>`.

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_primitives.py
"""Built-in linear primitives: forward shapes + adjoint correctness."""
from __future__ import annotations

import numpy as np
import pytest

from pwm_core.forward_compiler.primitives import get_primitive, PRIMITIVES


def _adjoint_inner_product_ok(prim, in_shape, params, seed=0, tol=1e-6):
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(in_shape).astype(np.float64)
    out_shape = prim.out_shape(in_shape, **params)
    y = rng.standard_normal(out_shape).astype(np.float64)
    Ax = prim.forward(x, **params).astype(np.float64)
    ATy = prim.adjoint(y, **params).astype(np.float64)
    lhs = float(np.sum(Ax.ravel() * y.ravel()))
    rhs = float(np.sum(x.ravel() * ATy.ravel()))
    denom = max(abs(lhs), abs(rhs), 1e-30)
    return abs(lhs - rhs) / denom < tol


def test_scale_forward_and_adjoint():
    p = get_primitive("scale")
    x = np.ones((3, 3), dtype=np.float32)
    assert np.allclose(p.forward(x, c=2.0), 2.0)
    assert p.out_shape((3, 3), c=2.0) == (3, 3)
    assert p.is_linear
    assert _adjoint_inner_product_ok(p, (3, 3), {"c": 2.0})


def test_mask_multiply_broadcasts_over_bands():
    p = get_primitive("mask_multiply")
    mask = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    x = np.ones((2, 2, 3), dtype=np.float32)
    y = p.forward(x, mask=mask)
    assert y.shape == (2, 2, 3)
    assert y[0, 1, 0] == 0.0 and y[0, 0, 0] == 1.0
    assert p.out_shape((2, 2, 3), mask=mask) == (2, 2, 3)
    assert _adjoint_inner_product_ok(p, (2, 2, 3), {"mask": mask.astype(np.float64)})


def test_band_sum_collapses_last_axis():
    p = get_primitive("band_sum")
    x = np.ones((2, 2, 4), dtype=np.float32)
    y = p.forward(x)
    assert y.shape == (2, 2)
    assert np.allclose(y, 4.0)
    assert p.out_shape((2, 2, 4)) == (2, 2)
    assert _adjoint_inner_product_ok(p, (2, 2, 4), {})


def test_band_shift_adjoint():
    p = get_primitive("band_shift")
    disp = {"dispersion_model": "poly", "disp_poly_x": [0.0, 1.0], "disp_poly_y": [0.0, 0.0]}
    in_shape = (8, 8, 4)
    assert p.out_shape(in_shape, dispersion=disp) == (8, 8, 4)
    assert _adjoint_inner_product_ok(p, in_shape, {"dispersion": disp}, tol=1e-4)


def test_unknown_primitive_raises():
    with pytest.raises(KeyError):
        get_primitive("does_not_exist")


def test_registry_contains_linear_builtins():
    for name in ("scale", "mask_multiply", "band_shift", "band_sum"):
        assert name in PRIMITIVES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_primitives.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pwm_core.forward_compiler.primitives'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/pwm_core/pwm_core/forward_compiler/primitives.py
"""Differentiable primitive operators for the forward-model compiler.

Each primitive composes into a CompiledOperator. Linear primitives provide an
exact adjoint (so the composed operator gets BaseOperator.check_adjoint and
torch autograd for free). Nonlinear / stochastic primitives set is_linear=False
and adjoint=None.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

import numpy as np

from pwm_core.mismatch.subpixel import subpixel_shift_2d
from pwm_core.physics.spectral.dispersion_models import dispersion_shift


@dataclass
class Primitive:
    name: str
    forward: Callable[..., np.ndarray]
    out_shape: Callable[..., Tuple[int, ...]]
    adjoint: Optional[Callable[..., np.ndarray]] = None
    is_linear: bool = True


PRIMITIVES: Dict[str, Primitive] = {}


def register_primitive(prim: Primitive) -> Primitive:
    PRIMITIVES[prim.name] = prim
    return prim


def get_primitive(name: str) -> Primitive:
    if name not in PRIMITIVES:
        raise KeyError(f"unknown primitive {name!r}; known: {sorted(PRIMITIVES)}")
    return PRIMITIVES[name]


# --- scale: y = c * x -------------------------------------------------------
register_primitive(Primitive(
    name="scale",
    forward=lambda x, c=1.0: (x * float(c)),
    adjoint=lambda y, c=1.0: (y * float(c)),
    out_shape=lambda in_shape, c=1.0: tuple(in_shape),
    is_linear=True,
))


# --- mask_multiply: y = x * mask (mask broadcast over trailing band axis) ----
def _mask_fwd(x, mask=None):
    m = np.asarray(mask)
    if x.ndim == m.ndim + 1:        # (H,W,L) * (H,W) -> broadcast over bands
        m = m[..., None]
    return x * m


def _mask_shape(in_shape, mask=None):
    return tuple(in_shape)


register_primitive(Primitive(
    name="mask_multiply",
    forward=_mask_fwd,
    adjoint=_mask_fwd,              # multiplication by a real mask is self-adjoint
    out_shape=_mask_shape,
    is_linear=True,
))


# --- band_sum: (H,W,L) -> (H,W) ---------------------------------------------
def _band_sum_fwd(x):
    return np.sum(x, axis=-1)


def _band_sum_adj(y, _n_bands):
    return np.repeat(y[..., None], _n_bands, axis=-1)


def _band_sum_shape(in_shape):
    if len(in_shape) < 3:
        raise ValueError(f"band_sum expects (...,L) with ndim>=3, got {in_shape}")
    return tuple(in_shape[:-1])


# band_sum adjoint needs to know L; we capture it from params if present.
def _band_sum_adjoint(y, n_bands=None):
    if n_bands is None:
        raise ValueError("band_sum adjoint requires n_bands param")
    return np.repeat(y[..., None], int(n_bands), axis=-1)


register_primitive(Primitive(
    name="band_sum",
    forward=lambda x, n_bands=None: _band_sum_fwd(x),
    adjoint=_band_sum_adjoint,
    out_shape=lambda in_shape, n_bands=None: _band_sum_shape(in_shape),
    is_linear=True,
))


# --- band_shift: shift each spectral band by dispersion (H,W,L)->(H,W,L) -----
def _band_shift_fwd(x, dispersion=None, sign=1.0):
    disp = dispersion or {}
    L = x.shape[-1]
    out = np.zeros_like(x)
    for l in range(L):
        dx, dy = dispersion_shift(disp, band=l)
        out[..., l] = subpixel_shift_2d(x[..., l], sign * dx, sign * dy)
    return out


def _band_shift_adj(y, dispersion=None, sign=1.0):
    return _band_shift_fwd(y, dispersion=dispersion, sign=-sign)


register_primitive(Primitive(
    name="band_shift",
    forward=_band_shift_fwd,
    adjoint=_band_shift_adj,
    out_shape=lambda in_shape, dispersion=None, sign=1.0: tuple(in_shape),
    is_linear=True,
))
```

> Note: `band_sum`'s adjoint needs the band count. The compiler (Task 4) injects `n_bands` into the `band_sum` stage params at compile time from the inferred input shape. The test above calls `prim.adjoint` with `n_bands` supplied via `_adjoint_inner_product_ok`'s params; update the test's `band_sum` case to pass it.

Adjust the `band_sum` test case to supply `n_bands`:

```python
def test_band_sum_collapses_last_axis():
    p = get_primitive("band_sum")
    x = np.ones((2, 2, 4), dtype=np.float32)
    y = p.forward(x)
    assert y.shape == (2, 2)
    assert np.allclose(y, 4.0)
    assert p.out_shape((2, 2, 4)) == (2, 2)
    assert _adjoint_inner_product_ok(p, (2, 2, 4), {"n_bands": 4})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_primitives.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/primitives.py packages/pwm_core/tests/test_fc_primitives.py
git commit -m "feat(forward-compiler): primitive registry + linear primitives (scale/mask/band_shift/band_sum)"
```

---

## Task 3: Nonlinear / stochastic primitives

**Files:**
- Modify: `packages/pwm_core/pwm_core/forward_compiler/primitives.py`
- Test: `packages/pwm_core/tests/test_fc_primitives.py` (add tests)

- [ ] **Step 1: Write the failing test (append to test_fc_primitives.py)**

```python
def test_square_magnitude_nonlinear_no_adjoint():
    p = get_primitive("square_magnitude")
    x = np.array([-2.0, 3.0], dtype=np.float64)
    assert np.allclose(p.forward(x), [4.0, 9.0])
    assert p.is_linear is False
    assert p.adjoint is None
    assert p.out_shape((2,)) == (2,)


def test_gaussian_noise_nonlinear_and_seeded():
    p = get_primitive("gaussian_noise")
    x = np.zeros((4, 4), dtype=np.float64)
    y1 = p.forward(x, sigma=0.5, seed=7)
    y2 = p.forward(x, sigma=0.5, seed=7)
    assert p.is_linear is False
    assert p.adjoint is None
    assert np.allclose(y1, y2)          # seeded => reproducible
    assert y1.std() > 0.0               # noise actually added
    assert p.out_shape((4, 4), sigma=0.5) == (4, 4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_primitives.py -k "nonlinear or gaussian" -v`
Expected: FAIL — `KeyError: "unknown primitive 'square_magnitude'..."`

- [ ] **Step 3: Write minimal implementation (append to primitives.py)**

```python
# --- square_magnitude: y = x**2 (intensity / phase-retrieval forward) --------
register_primitive(Primitive(
    name="square_magnitude",
    forward=lambda x: np.abs(x) ** 2,
    adjoint=None,
    out_shape=lambda in_shape: tuple(in_shape),
    is_linear=False,
))


# --- gaussian_noise: y = x + N(0, sigma^2), seeded for reproducibility -------
def _gaussian_noise_fwd(x, sigma=0.0, seed=0):
    rng = np.random.default_rng(int(seed))
    return x + rng.standard_normal(x.shape) * float(sigma)


register_primitive(Primitive(
    name="gaussian_noise",
    forward=_gaussian_noise_fwd,
    adjoint=None,
    out_shape=lambda in_shape, sigma=0.0, seed=0: tuple(in_shape),
    is_linear=False,
))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_primitives.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/primitives.py packages/pwm_core/tests/test_fc_primitives.py
git commit -m "feat(forward-compiler): nonlinear/stochastic primitives (square_magnitude, gaussian_noise)"
```

---

## Task 4: CompiledOperator + compile_model()

**Files:**
- Create: `packages/pwm_core/pwm_core/forward_compiler/compiler.py`
- Modify: `packages/pwm_core/pwm_core/forward_compiler/__init__.py`
- Test: `packages/pwm_core/tests/test_fc_compiler.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_compiler.py
"""compile_model: composition, shape inference, adjoint, linearity flags."""
from __future__ import annotations

import numpy as np
import pytest

from pwm_core.forward_compiler import ForwardModel, Stage, compile_model
from pwm_core.physics.base import BaseOperator


def _cassi_model(H=8, W=8, L=4):
    mask = np.random.default_rng(1).integers(0, 2, size=(H, W)).astype(np.float64)
    disp = {"dispersion_model": "poly", "disp_poly_x": [0.0, 1.0], "disp_poly_y": [0.0, 0.0]}
    return ForwardModel(
        name="cassi_demo",
        x_shape=(H, W, L),
        stages=[
            Stage(op="band_shift", params={"dispersion": disp}),
            Stage(op="mask_multiply", params={"mask": mask}),
            Stage(op="band_sum", params={}),
        ],
        metadata={"modality": "cassi"},
    )


def test_compiled_operator_is_physics_operator():
    op = compile_model(_cassi_model())
    assert isinstance(op, BaseOperator)
    assert op.x_shape == (8, 8, 4)
    assert op.y_shape == (8, 8)
    assert op.is_linear is True
    assert op.supports_autodiff is True


def test_compiled_forward_shapes():
    op = compile_model(_cassi_model())
    x = np.random.default_rng(0).standard_normal((8, 8, 4))
    y = op.forward(x)
    assert y.shape == (8, 8)


def test_compiled_operator_passes_builtin_adjoint_check():
    op = compile_model(_cassi_model())
    report = op.check_adjoint(n_trials=3, tol=1e-4)
    assert report.passed, report.summary()


def test_nonlinear_model_blocks_adjoint():
    m = ForwardModel(
        name="intensity",
        x_shape=(4, 4),
        stages=[Stage(op="square_magnitude", params={})],
    )
    op = compile_model(m)
    assert op.is_linear is False
    assert op.supports_autodiff is False
    with pytest.raises(ValueError, match="non-linear"):
        op.adjoint(np.ones((4, 4)))


def test_band_sum_n_bands_injected():
    # band_sum adjoint needs n_bands; compiler must inject it from inferred shape.
    op = compile_model(_cassi_model(L=5))
    # adjoint should reconstruct a 5-band cube
    back = op.adjoint(np.ones((8, 8)))
    assert back.shape == (8, 8, 5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_compiler.py -v`
Expected: FAIL — `ImportError: cannot import name 'compile_model'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/pwm_core/pwm_core/forward_compiler/compiler.py
"""Compile a ForwardModel into an executable CompiledOperator (a BaseOperator).

forward = primitives applied left->right; adjoint = primitive adjoints applied
right->left (linear models only). The operator inherits BaseOperator.check_adjoint
(inner-product test) and serialize/metadata for free.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np

from pwm_core.forward_compiler.ir import ForwardModel, Stage
from pwm_core.forward_compiler.primitives import Primitive, get_primitive
from pwm_core.physics.base import BaseOperator


class CompiledOperator(BaseOperator):
    """A BaseOperator produced by compiling a ForwardModel."""

    def __init__(self, model: ForwardModel,
                 x_shape: Tuple[int, ...], y_shape: Tuple[int, ...],
                 stages_resolved: List[Tuple[Primitive, Dict[str, Any]]]) -> None:
        # BaseOperator is a dataclass; we set its attributes directly rather
        # than invoking its generated __init__.
        self.operator_id = model.name
        self.theta = {}
        self.model = model
        self._x_shape = tuple(x_shape)
        self._y_shape = tuple(y_shape)
        self._stages = stages_resolved
        self._is_linear = all(p.is_linear for p, _ in stages_resolved)
        self._supports_autodiff = self._is_linear

    def forward(self, x: np.ndarray) -> np.ndarray:
        cur = np.asarray(x)
        for prim, params in self._stages:
            cur = prim.forward(cur, **params)
        return cur

    def adjoint(self, y: np.ndarray) -> np.ndarray:
        if not self._is_linear:
            raise ValueError(
                f"operator {self.operator_id!r} is non-linear; adjoint is undefined")
        cur = np.asarray(y)
        for prim, params in reversed(self._stages):
            if prim.adjoint is None:
                raise ValueError(f"primitive {prim.name!r} has no adjoint")
            cur = prim.adjoint(cur, **params)
        return cur


def compile_model(model: ForwardModel) -> CompiledOperator:
    """Resolve primitives, propagate shapes, inject derived params, return op."""
    shape: Tuple[int, ...] = tuple(model.x_shape)
    resolved: List[Tuple[Primitive, Dict[str, Any]]] = []
    for stage in model.stages:
        prim = get_primitive(stage.op)
        params = dict(stage.params)
        # band_sum's adjoint needs the band count from the *input* shape.
        if stage.op == "band_sum" and "n_bands" not in params:
            if len(shape) < 3:
                raise ValueError(
                    f"band_sum stage requires a (...,L) input, got shape {shape}")
            params["n_bands"] = int(shape[-1])
        out_shape = prim.out_shape(shape, **params)
        resolved.append((prim, params))
        shape = tuple(int(d) for d in out_shape)
    return CompiledOperator(model, x_shape=tuple(model.x_shape),
                            y_shape=shape, stages_resolved=resolved)
```

Update `__init__.py`:

```python
# packages/pwm_core/pwm_core/forward_compiler/__init__.py
"""pwm_core.forward_compiler

Forward-model compiler: a structured description of an imaging forward model
(an ordered pipeline of primitive ops) compiled into an executable, validated
pwm_core PhysicsOperator.
"""
from __future__ import annotations

from pwm_core.forward_compiler.ir import ForwardModel, Stage
from pwm_core.forward_compiler.primitives import (
    PRIMITIVES, Primitive, get_primitive, register_primitive,
)
from pwm_core.forward_compiler.compiler import CompiledOperator, compile_model

__all__ = [
    "ForwardModel", "Stage",
    "PRIMITIVES", "Primitive", "get_primitive", "register_primitive",
    "CompiledOperator", "compile_model",
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_compiler.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/compiler.py packages/pwm_core/pwm_core/forward_compiler/__init__.py packages/pwm_core/tests/test_fc_compiler.py
git commit -m "feat(forward-compiler): CompiledOperator + compile_model with shape inference"
```

---

## Task 5: as_torch() differentiable wrapper (linear models)

**Files:**
- Modify: `packages/pwm_core/pwm_core/forward_compiler/compiler.py`
- Test: `packages/pwm_core/tests/test_fc_torch.py`

The "differentiable simulator" promise: a linear `CompiledOperator` becomes a `torch.autograd.Function` whose backward is the operator's adjoint (the exact vjp for a linear map). Gradients flow through the simulator for end-to-end design downstream.

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_torch.py
"""as_torch: a linear CompiledOperator is differentiable (backward = adjoint)."""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from pwm_core.forward_compiler import ForwardModel, Stage, compile_model
from pwm_core.forward_compiler.compiler import as_torch


def _scale_mask_model(H=4, W=4, L=2, c=3.0):
    mask = np.random.default_rng(2).random((H, W))
    return ForwardModel(
        name="lin_demo",
        x_shape=(H, W, L),
        stages=[
            Stage(op="scale", params={"c": c}),
            Stage(op="mask_multiply", params={"mask": mask}),
            Stage(op="band_sum", params={}),
        ],
    )


def test_as_torch_forward_matches_numpy():
    op = compile_model(_scale_mask_model())
    fn = as_torch(op)
    x = np.random.default_rng(0).standard_normal((4, 4, 2))
    y_np = op.forward(x)
    y_t = fn(torch.tensor(x, dtype=torch.float64, requires_grad=True))
    assert np.allclose(y_t.detach().numpy(), y_np, atol=1e-6)


def test_as_torch_grad_equals_adjoint():
    op = compile_model(_scale_mask_model())
    fn = as_torch(op)
    x = torch.tensor(np.random.default_rng(0).standard_normal((4, 4, 2)),
                     dtype=torch.float64, requires_grad=True)
    y = fn(x)
    y.sum().backward()              # d/dx sum(A x) = A^T(ones)
    expected = op.adjoint(np.ones(op.y_shape))
    assert np.allclose(x.grad.numpy(), expected, atol=1e-6)


def test_as_torch_rejects_nonlinear():
    m = ForwardModel(name="nl", x_shape=(4,),
                     stages=[Stage(op="square_magnitude", params={})])
    op = compile_model(m)
    with pytest.raises(ValueError, match="linear"):
        as_torch(op)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_torch.py -v`
Expected: FAIL — `ImportError: cannot import name 'as_torch'`

- [ ] **Step 3: Write minimal implementation (append to compiler.py)**

```python
def as_torch(op: CompiledOperator):
    """Wrap a *linear* CompiledOperator as a differentiable torch callable.

    Returns a function f(x: Tensor) -> Tensor whose backward applies the
    operator's adjoint (the exact vjp for a linear map). Raises if the operator
    is non-linear.
    """
    if not op.is_linear:
        raise ValueError(
            f"as_torch requires a linear operator; {op.operator_id!r} is non-linear")
    import torch

    class _OpFn(torch.autograd.Function):
        @staticmethod
        def forward(ctx, x):
            dtype, device = x.dtype, x.device
            ctx._meta = (dtype, device)
            y = op.forward(x.detach().cpu().numpy())
            return torch.as_tensor(np.asarray(y), dtype=dtype, device=device)

        @staticmethod
        def backward(ctx, grad_out):
            dtype, device = ctx._meta
            gx = op.adjoint(grad_out.detach().cpu().numpy())
            return torch.as_tensor(np.asarray(gx), dtype=dtype, device=device)

    return _OpFn.apply
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_torch.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/compiler.py packages/pwm_core/tests/test_fc_torch.py
git commit -m "feat(forward-compiler): as_torch() differentiable wrapper for linear models"
```

---

## Task 6: Validators + ForwardModelReport

**Files:**
- Create: `packages/pwm_core/pwm_core/forward_compiler/validate.py`
- Modify: `packages/pwm_core/pwm_core/forward_compiler/__init__.py`
- Test: `packages/pwm_core/tests/test_fc_validate.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_validate.py
"""Validators: dimensions, linearity classification, conditioning, report."""
from __future__ import annotations

import numpy as np
import pytest

from pwm_core.forward_compiler import ForwardModel, Stage, compile_model
from pwm_core.forward_compiler.validate import (
    validate_dimensions, classify_linearity, probe_conditioning,
    validate_forward_model, ForwardModelReport,
)


def _cassi_model(H=8, W=8, L=4):
    mask = np.random.default_rng(1).integers(0, 2, size=(H, W)).astype(np.float64)
    disp = {"dispersion_model": "poly", "disp_poly_x": [0.0, 1.0], "disp_poly_y": [0.0, 0.0]}
    return ForwardModel(
        name="cassi_demo", x_shape=(H, W, L),
        stages=[Stage(op="band_shift", params={"dispersion": disp}),
                Stage(op="mask_multiply", params={"mask": mask}),
                Stage(op="band_sum", params={})],
        metadata={"modality": "cassi"})


def test_validate_dimensions_ok():
    ok, msg, y_shape = validate_dimensions(_cassi_model())
    assert ok, msg
    assert y_shape == (8, 8)


def test_validate_dimensions_catches_bad_pipeline():
    # band_sum on a 2-D input is invalid (needs a band axis)
    bad = ForwardModel(name="bad", x_shape=(8, 8),
                       stages=[Stage(op="band_sum", params={})])
    ok, msg, _ = validate_dimensions(bad)
    assert not ok
    assert "band_sum" in msg


def test_classify_linearity_linear_op():
    op = compile_model(_cassi_model())
    res = classify_linearity(op)
    assert res["is_linear"] is True
    assert res["max_residual"] < 1e-6


def test_classify_linearity_nonlinear_op():
    m = ForwardModel(name="nl", x_shape=(4, 4),
                     stages=[Stage(op="square_magnitude", params={})])
    op = compile_model(m)
    res = classify_linearity(op)
    assert res["is_linear"] is False
    assert res["max_residual"] > 1e-3


def test_probe_conditioning_returns_spectral_norm():
    op = compile_model(_cassi_model())
    res = probe_conditioning(op, n_iter=30)
    assert res["spectral_norm"] > 0.0
    assert 0.0 <= res["energy_ratio"] <= 2.0


def test_validate_forward_model_report():
    rep = validate_forward_model(_cassi_model())
    assert isinstance(rep, ForwardModelReport)
    assert rep.ok is True
    assert rep.is_linear is True
    assert rep.adjoint is not None and rep.adjoint.passed
    assert rep.y_shape == (8, 8)
    assert "spectral_norm" in rep.conditioning
    s = rep.summary()
    assert "cassi_demo" in s


def test_validate_forward_model_nonlinear_skips_adjoint():
    m = ForwardModel(name="nl", x_shape=(4, 4),
                     stages=[Stage(op="square_magnitude", params={})])
    rep = validate_forward_model(m)
    assert rep.is_linear is False
    assert rep.adjoint is None
    assert any("non-linear" in w for w in rep.warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pwm_core.forward_compiler.validate'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/pwm_core/pwm_core/forward_compiler/validate.py
"""Validators for compiled forward models.

Produces a ForwardModelReport: dimension check, adjoint dot-product test
(linear only), linearity classification (superposition probe), and a
conditioning probe (power-iteration spectral norm + energy ratio).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from pwm_core.forward_compiler.ir import ForwardModel
from pwm_core.forward_compiler.compiler import CompiledOperator, compile_model
from pwm_core.physics.base import AdjointCheckReport


@dataclass
class ForwardModelReport:
    name: str
    x_shape: Tuple[int, ...]
    y_shape: Tuple[int, ...]
    is_linear: bool
    adjoint: Optional[AdjointCheckReport]
    linearity_probe: Dict[str, Any]
    conditioning: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    ok: bool = True

    def summary(self) -> str:
        adj = self.adjoint.summary() if self.adjoint else "adjoint=N/A (non-linear)"
        return (f"ForwardModelReport[{self.name}] ok={self.ok} linear={self.is_linear} "
                f"x{self.x_shape}->y{self.y_shape} | {adj} | "
                f"||A||~{self.conditioning.get('spectral_norm', float('nan')):.3g}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "x_shape": list(self.x_shape),
            "y_shape": list(self.y_shape),
            "is_linear": self.is_linear,
            "adjoint": (None if self.adjoint is None else {
                "passed": self.adjoint.passed,
                "max_relative_error": self.adjoint.max_relative_error,
                "tolerance": self.adjoint.tolerance,
            }),
            "linearity_probe": self.linearity_probe,
            "conditioning": self.conditioning,
            "warnings": list(self.warnings),
            "ok": self.ok,
        }


def validate_dimensions(model: ForwardModel) -> Tuple[bool, str, Optional[Tuple[int, ...]]]:
    """Compile (which propagates shapes) and report success/failure."""
    try:
        op = compile_model(model)
        return True, "ok", op.y_shape
    except Exception as exc:  # noqa: BLE001 - report any shape/primitive error
        return False, f"{type(exc).__name__}: {exc}", None


def classify_linearity(op: CompiledOperator, seed: int = 0,
                       n_trials: int = 3, tol: float = 1e-6) -> Dict[str, Any]:
    """Probe A(a*x + b*z) ?= a*A(x) + b*A(z)."""
    rng = np.random.default_rng(seed)
    max_res = 0.0
    for _ in range(n_trials):
        x = rng.standard_normal(op.x_shape)
        z = rng.standard_normal(op.x_shape)
        a, b = float(rng.standard_normal()), float(rng.standard_normal())
        lhs = op.forward(a * x + b * z)
        rhs = a * op.forward(x) + b * op.forward(z)
        denom = max(float(np.linalg.norm(rhs.ravel())), 1e-30)
        res = float(np.linalg.norm((lhs - rhs).ravel())) / denom
        max_res = max(max_res, res)
    return {"is_linear": bool(max_res < tol), "max_residual": max_res}


def probe_conditioning(op: CompiledOperator, n_iter: int = 30,
                       seed: int = 0) -> Dict[str, Any]:
    """Power-iteration estimate of the spectral norm ||A|| and an energy ratio.

    energy_ratio = ||A x|| / ||x|| for a random unit-ish x (a coarse
    well-posedness signal). Requires a linear operator (uses adjoint)."""
    if not op.is_linear:
        return {"spectral_norm": None, "energy_ratio": None,
                "note": "conditioning probe requires a linear operator"}
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(op.x_shape)
    x = x / max(float(np.linalg.norm(x.ravel())), 1e-30)
    sigma = 0.0
    for _ in range(n_iter):
        Ax = op.forward(x)
        ATAx = op.adjoint(Ax)
        nrm = float(np.linalg.norm(ATAx.ravel()))
        if nrm < 1e-30:
            break
        x = ATAx / nrm
        sigma = np.sqrt(nrm)
    x0 = rng.standard_normal(op.x_shape)
    energy_ratio = (float(np.linalg.norm(op.forward(x0).ravel())) /
                    max(float(np.linalg.norm(x0.ravel())), 1e-30))
    return {"spectral_norm": float(sigma), "energy_ratio": float(energy_ratio)}


def validate_forward_model(model: ForwardModel) -> ForwardModelReport:
    warnings: List[str] = []
    ok, msg, y_shape = validate_dimensions(model)
    if not ok:
        return ForwardModelReport(
            name=model.name, x_shape=tuple(model.x_shape), y_shape=(),
            is_linear=False, adjoint=None, linearity_probe={},
            conditioning={}, warnings=[f"dimension error: {msg}"], ok=False)

    op = compile_model(model)
    lin = classify_linearity(op)
    cond = probe_conditioning(op)

    adjoint_report = None
    if op.is_linear:
        adjoint_report = op.check_adjoint(n_trials=3, tol=1e-4)
        if not adjoint_report.passed:
            warnings.append(f"adjoint check failed: {adjoint_report.summary()}")
    else:
        warnings.append("operator is non-linear; adjoint test skipped")

    overall_ok = ok and (adjoint_report is None or adjoint_report.passed)
    return ForwardModelReport(
        name=model.name, x_shape=tuple(op.x_shape), y_shape=tuple(op.y_shape),
        is_linear=op.is_linear, adjoint=adjoint_report, linearity_probe=lin,
        conditioning=cond, warnings=warnings, ok=overall_ok)
```

Append to `__init__.py` exports:

```python
from pwm_core.forward_compiler.validate import (
    ForwardModelReport, validate_forward_model, validate_dimensions,
    classify_linearity, probe_conditioning,
)
```

And add those names to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_validate.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/validate.py packages/pwm_core/pwm_core/forward_compiler/__init__.py packages/pwm_core/tests/test_fc_validate.py
git commit -m "feat(forward-compiler): validators + ForwardModelReport (dims/adjoint/linearity/conditioning)"
```

---

## Task 7: Bridge from modality / digital-twin spec fields

**Files:**
- Create: `packages/pwm_core/pwm_core/forward_compiler/bridge.py`
- Modify: `packages/pwm_core/pwm_core/forward_compiler/__init__.py`
- Test: `packages/pwm_core/tests/test_fc_bridge.py`

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_bridge.py
"""bridge: modality template -> ForwardModel, and spec-fields -> ForwardModel."""
from __future__ import annotations

import numpy as np
import pytest

from pwm_core.forward_compiler import compile_model
from pwm_core.forward_compiler.bridge import from_modality, from_spec_fields


def test_from_modality_cassi_builds_three_stages():
    mask = np.random.default_rng(0).integers(0, 2, (8, 8)).astype(np.float64)
    disp = {"dispersion_model": "poly", "disp_poly_x": [0.0, 1.0], "disp_poly_y": [0.0, 0.0]}
    m = from_modality("cassi", H=8, W=8, N_bands=4, mask=mask, dispersion=disp)
    assert [s.op for s in m.stages] == ["band_shift", "mask_multiply", "band_sum"]
    assert m.x_shape == (8, 8, 4)
    op = compile_model(m)
    assert op.y_shape == (8, 8)
    assert op.check_adjoint(n_trials=2, tol=1e-4).passed


def test_from_modality_unknown_raises():
    with pytest.raises(ValueError, match="unknown modality"):
        from_modality("not_a_modality", H=4, W=4)


def test_from_spec_fields_cassi():
    mask = np.ones((8, 8), dtype=np.float64)
    fields = {
        "spec_type": "cassi",
        "six_tuple": {"omega": {"H": 8, "W": 8, "N_bands": 4}},
        "protocol_fields": {"disp_a1_nominal": 1.0},
    }
    m = from_spec_fields(fields, mask=mask)
    assert m.metadata.get("modality") == "cassi"
    assert m.x_shape == (8, 8, 4)
    op = compile_model(m)
    assert op.y_shape == (8, 8)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pwm_core.forward_compiler.bridge'`

- [ ] **Step 3: Write minimal implementation**

```python
# packages/pwm_core/pwm_core/forward_compiler/bridge.py
"""Bridge: build ForwardModels from modality templates or digital-twin specs.

The agent's NL/equation reasoning produces a modality name + dimensions; this
bridge turns that into the concrete primitive pipeline. Array assets (e.g. the
coded-aperture mask) are passed in directly.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np

from pwm_core.forward_compiler.ir import ForwardModel, Stage


def from_modality(modality: str, *, H: int, W: int, N_bands: int = 1,
                  mask: Optional[np.ndarray] = None,
                  dispersion: Optional[Dict[str, Any]] = None) -> ForwardModel:
    """Return a ForwardModel for a known modality template."""
    modality = modality.lower()
    if modality == "cassi":
        if mask is None:
            mask = np.ones((H, W), dtype=np.float64)
        disp = dispersion or {
            "dispersion_model": "poly",
            "disp_poly_x": [0.0, 1.0],
            "disp_poly_y": [0.0, 0.0],
        }
        return ForwardModel(
            name=f"cassi_{H}x{W}x{N_bands}",
            x_shape=(H, W, N_bands),
            stages=[
                Stage(op="band_shift", params={"dispersion": disp}),
                Stage(op="mask_multiply", params={"mask": np.asarray(mask, dtype=np.float64)}),
                Stage(op="band_sum", params={}),
            ],
            metadata={"modality": "cassi"},
        )
    raise ValueError(f"unknown modality {modality!r}; known templates: ['cassi']")


def from_spec_fields(fields: Dict[str, Any], *,
                     mask: Optional[np.ndarray] = None) -> ForwardModel:
    """Build a ForwardModel from digital-twin spec fields (six_tuple/protocol).

    Recognises the same field layout produced by the optics pwm_bridge.
    """
    modality = (fields.get("spec_type") or fields.get("modality") or "").lower()
    omega = (fields.get("six_tuple") or {}).get("omega", {})
    H = int(omega.get("H", 0)) or int(fields.get("H", 0))
    W = int(omega.get("W", 0)) or int(fields.get("W", 0))
    N_bands = int(omega.get("N_bands", 1) or 1)
    if modality == "cassi":
        pf = fields.get("protocol_fields", {})
        a1 = float(pf.get("disp_a1_nominal", 1.0))
        disp = {"dispersion_model": "poly",
                "disp_poly_x": [0.0, a1], "disp_poly_y": [0.0, 0.0]}
        return from_modality("cassi", H=H, W=W, N_bands=N_bands,
                             mask=mask, dispersion=disp)
    raise ValueError(f"from_spec_fields: unsupported modality {modality!r}")
```

Append to `__init__.py` exports: `from pwm_core.forward_compiler.bridge import from_modality, from_spec_fields` and add to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_bridge.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/bridge.py packages/pwm_core/pwm_core/forward_compiler/__init__.py packages/pwm_core/tests/test_fc_bridge.py
git commit -m "feat(forward-compiler): bridge from modality template + digital-twin spec fields"
```

---

## Task 8: Golden fidelity test vs CASSIOperator + registry registration

**Files:**
- Modify: `packages/pwm_core/pwm_core/forward_compiler/__init__.py` (register a compiled-operator factory in GLOBAL_REGISTRY)
- Test: `packages/pwm_core/tests/test_fc_golden_cassi.py`

This proves "compile to pwm_core.physics": the compiled CASSI forward must match the hand-written `CASSIOperator` forward within tolerance, and the compiler must be discoverable via the shared operator registry.

- [ ] **Step 1: Write the failing test**

```python
# packages/pwm_core/tests/test_fc_golden_cassi.py
"""Golden test: compiled CASSI forward matches hand-written CASSIOperator."""
from __future__ import annotations

import numpy as np

from pwm_core.forward_compiler import compile_model
from pwm_core.forward_compiler.bridge import from_modality
from pwm_core.physics.spectral.cassi_operator import CASSIOperator
from pwm_core.core.registry import get_registry


def test_compiled_cassi_matches_handwritten():
    H, W, L = 12, 12, 6
    rng = np.random.default_rng(7)
    mask = rng.integers(0, 2, (H, W)).astype(np.float32)
    theta = {"L": L, "dispersion_model": "poly",
             "disp_poly_x": [0.0, 1.0], "disp_poly_y": [0.0, 0.0]}

    hand = CASSIOperator(operator_id="cassi", theta=theta, mask=mask)
    cube = rng.standard_normal((H, W, L)).astype(np.float32)
    y_hand = hand.forward(cube)

    model = from_modality("cassi", H=H, W=W, N_bands=L,
                          mask=mask.astype(np.float64),
                          dispersion={"dispersion_model": "poly",
                                      "disp_poly_x": [0.0, 1.0],
                                      "disp_poly_y": [0.0, 0.0]})
    op = compile_model(model)
    y_comp = op.forward(cube.astype(np.float64))

    assert y_comp.shape == y_hand.shape
    assert np.allclose(y_comp, y_hand, atol=1e-4), \
        f"max abs diff {np.max(np.abs(y_comp - y_hand))}"


def test_compiler_factory_registered():
    reg = get_registry()
    assert "forward_compiler" in reg.operators
    factory = reg.operators["forward_compiler"]
    op = factory(from_modality("cassi", H=8, W=8, N_bands=4))
    assert op.y_shape == (8, 8)
```

> Note: `CASSIOperator` is a dataclass subclass of `BaseOperator`; verify its constructor accepts `operator_id`, `theta`, `mask`. If `BaseOperator`'s dataclass field order differs, construct with keyword args only (as above). If `operator_id` is not a field, drop it and set `hand.operator_id = "cassi"` after construction.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_golden_cassi.py -v`
Expected: FAIL — `test_compiler_factory_registered` fails (`"forward_compiler" not in reg.operators`); the golden test may pass already (good) or reveal a convention mismatch to fix.

- [ ] **Step 3: Write minimal implementation (append to `__init__.py`)**

```python
# Register the compiler as a shared-registry operator factory so other pwm_core
# code can build operators from a ForwardModel via the standard registry.
def _register_in_global_registry() -> None:
    from pwm_core.core.registry import get_registry
    get_registry().register_operator("forward_compiler", compile_model)


_register_in_global_registry()
```

If the golden test reveals a sign/order mismatch with `CASSIOperator`, align the `band_shift` primitive's sign convention in `primitives.py` (the hand-written operator shifts each band by `+dispersion_shift` before masking — the `from_modality` template already matches this; only adjust if the test shows otherwise).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_golden_cassi.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add packages/pwm_core/pwm_core/forward_compiler/__init__.py packages/pwm_core/tests/test_fc_golden_cassi.py
git commit -m "feat(forward-compiler): golden fidelity vs CASSIOperator + registry registration"
```

---

## Task 9: AI4Science tool layer — fm_primitives + model JSON dump/load

**Files:**
- Create: `AI4Science/ai4science/harness/forward_model_tools.py`
- Test: `AI4Science/tests/test_forward_model_tools.py`

The tool layer turns the array-native IR into workspace-persistable JSON: array params are stored as `{"$ref": "name.npy"}` alongside saved `.npy` files. `fm_primitives` is read-only; the dump/load helpers underpin compile/simulate.

- [ ] **Step 1: Write the failing test**

```python
# AI4Science/tests/test_forward_model_tools.py
"""forward_model_tools: primitives listing + model JSON ref round-trip + tools."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ai4science.harness.forward_model_tools import (
    forward_model_tools, dump_model_json, load_model_json, TOOL_PRICES,
)
from pwm_core.forward_compiler.bridge import from_modality


def test_fm_primitives_lists_builtins(tmp_path):
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    out = json.loads(tools["fm_primitives"].func(str(tmp_path)))
    names = {p["name"] for p in out["primitives"]}
    assert {"scale", "mask_multiply", "band_shift", "band_sum",
            "square_magnitude", "gaussian_noise"} <= names
    linear = {p["name"]: p["is_linear"] for p in out["primitives"]}
    assert linear["mask_multiply"] is True
    assert linear["square_magnitude"] is False


def test_model_json_ref_roundtrip(tmp_path):
    mask = np.random.default_rng(0).integers(0, 2, (8, 8)).astype(np.float64)
    model = from_modality("cassi", H=8, W=8, N_bands=4, mask=mask)
    dump_model_json(model, tmp_path, "forward_model.json")
    # array param must be externalized as a $ref + a saved .npy
    raw = json.loads((tmp_path / "forward_model.json").read_text())
    mm = [s for s in raw["stages"] if s["op"] == "mask_multiply"][0]
    assert isinstance(mm["params"]["mask"], dict) and "$ref" in mm["params"]["mask"]
    assert (tmp_path / mm["params"]["mask"]["$ref"]).exists()
    # round-trip restores the array
    model2 = load_model_json(tmp_path, "forward_model.json")
    mm2 = [s for s in model2.stages if s.op == "mask_multiply"][0]
    assert np.allclose(mm2.params["mask"], mask)


def test_tool_prices_present():
    for name in ("fm_compile", "fm_validate", "fm_simulate"):
        assert name in TOOL_PRICES
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai4science.harness.forward_model_tools'`

- [ ] **Step 3: Write minimal implementation**

```python
# AI4Science/ai4science/harness/forward_model_tools.py
"""Forward-model compiler agent tools (science-tier, PWM-metered).

Exposes the pwm_core.forward_compiler to agents: list primitives, compile a
structured ForwardModel (with validation), validate an existing compiled model,
and run the compiled forward to produce a measurement. Array params (masks etc.)
are externalized to .npy + {"$ref": ...} for JSON persistence.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from ai4science.harness.tools.base import Tool
from pwm_core.forward_compiler import (
    ForwardModel, Stage, PRIMITIVES, compile_model, validate_forward_model,
)

# PWM price per call (moat tool; mirrors optics-design metering).
TOOL_PRICES: Dict[str, float] = {
    "fm_primitives": 0.0,     # read-only discovery, free
    "fm_compile": 0.02,
    "fm_validate": 0.01,
    "fm_simulate": 0.02,
}


# --- JSON <-> IR with array externalization ---------------------------------

def dump_model_json(model: ForwardModel, workspace: Path, name: str) -> Path:
    workspace = Path(workspace)
    d = model.to_dict()
    for i, stage in enumerate(d["stages"]):
        for key, val in list(stage["params"].items()):
            if isinstance(val, np.ndarray):
                ref = f"_fm_{model.name}_{i}_{key}.npy"
                np.save(workspace / ref, val)
                stage["params"][key] = {"$ref": ref}
    path = workspace / name
    path.write_text(json.dumps(d, indent=2))
    return path


def load_model_json(workspace: Path, name: str) -> ForwardModel:
    workspace = Path(workspace)
    d = json.loads((workspace / name).read_text())
    for stage in d["stages"]:
        for key, val in list(stage["params"].items()):
            if isinstance(val, dict) and "$ref" in val:
                stage["params"][key] = np.load(workspace / val["$ref"])
    return ForwardModel.from_dict(d)


# --- tool funcs -------------------------------------------------------------

def _fm_primitives(workspace: str) -> str:
    prims = [{"name": p.name, "is_linear": p.is_linear,
              "has_adjoint": p.adjoint is not None}
             for p in PRIMITIVES.values()]
    return json.dumps({"ok": True, "primitives": sorted(prims, key=lambda p: p["name"])})


def _resolve_model(workspace: Path, model: Optional[str], model_path: str) -> ForwardModel:
    if model:
        d = json.loads(model)
        # inline arrays may be given as $ref too; reuse loader semantics
        for stage in d.get("stages", []):
            for key, val in list(stage.get("params", {}).items()):
                if isinstance(val, dict) and "$ref" in val:
                    stage["params"][key] = np.load(workspace / val["$ref"])
        return ForwardModel.from_dict(d)
    return load_model_json(workspace, model_path)


def _fm_compile(workspace: str, model: Optional[str] = None,
                model_path: str = "forward_model_in.json",
                out: str = "forward_model.json") -> str:
    ws = Path(workspace)
    fm = _resolve_model(ws, model, model_path)
    report = validate_forward_model(fm)
    dump_model_json(fm, ws, out)
    (ws / "forward_model_report.json").write_text(json.dumps(report.to_dict(), indent=2))
    return json.dumps({"ok": report.ok, "model": out,
                       "report": "forward_model_report.json",
                       "summary": report.summary()})


def _fm_validate(workspace: str, model_path: str = "forward_model.json") -> str:
    ws = Path(workspace)
    fm = load_model_json(ws, model_path)
    report = validate_forward_model(fm)
    (ws / "forward_model_report.json").write_text(json.dumps(report.to_dict(), indent=2))
    return json.dumps({"ok": report.ok, "summary": report.summary(),
                       "report": report.to_dict()})


def _fm_simulate(workspace: str, model_path: str = "forward_model.json",
                 x: Optional[str] = None, out: str = "y.npy", seed: int = 0) -> str:
    ws = Path(workspace)
    fm = load_model_json(ws, model_path)
    op = compile_model(fm)
    if x:
        x_arr = np.load(ws / x)
    else:
        x_arr = np.random.default_rng(int(seed)).standard_normal(op.x_shape)
    y = op.forward(x_arr.astype(np.float64))
    np.save(ws / out, y)
    return json.dumps({"ok": True, "x_shape": list(op.x_shape),
                       "y_shape": list(np.asarray(y).shape), "out": out})


def forward_model_tools(gate_provider: Optional[Callable] = None,
                        workspace: Optional[Path] = None) -> List[Tool]:
    """Build the forward-model tool bundle.

    gate_provider is accepted for parity with other moat bundles (optics);
    PWM metering is applied by the harness via TOOL_PRICES when a gate exists.
    """
    return [
        Tool(name="fm_primitives",
             description="List the forward-model compiler's primitive ops "
                         "(name, linear, has_adjoint). Use this to compose a model.",
             parameters={"type": "object", "properties": {}},
             func=_fm_primitives, mutating=False),
        Tool(name="fm_compile",
             description="Compile + validate a structured ForwardModel. Provide "
                         "either `model` (JSON string of {name,x_shape,stages,...}) "
                         "or `model_path` (a JSON file in the workspace). Writes "
                         "forward_model.json + forward_model_report.json. Array "
                         "params use {\"$ref\":\"file.npy\"}.",
             parameters={"type": "object", "properties": {
                 "model": {"type": "string", "description": "Inline ForwardModel JSON"},
                 "model_path": {"type": "string", "default": "forward_model_in.json"},
                 "out": {"type": "string", "default": "forward_model.json"}}},
             func=_fm_compile, mutating=True),
        Tool(name="fm_validate",
             description="Validate an already-compiled forward_model.json: adjoint "
                         "dot-product test, linearity, conditioning. Writes the report.",
             parameters={"type": "object", "properties": {
                 "model_path": {"type": "string", "default": "forward_model.json"}}},
             func=_fm_validate, mutating=True),
        Tool(name="fm_simulate",
             description="Run the compiled forward operator to produce a measurement "
                         "y.npy (random x if none supplied).",
             parameters={"type": "object", "properties": {
                 "model_path": {"type": "string", "default": "forward_model.json"},
                 "x": {"type": "string", "description": "optional input .npy"},
                 "out": {"type": "string", "default": "y.npy"},
                 "seed": {"type": "integer", "default": 0}}},
             func=_fm_simulate, mutating=True),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add AI4Science/ai4science/harness/forward_model_tools.py AI4Science/tests/test_forward_model_tools.py
git commit -m "feat(forward-compiler): AI4Science fm_primitives tool + model JSON ref round-trip"
```

---

## Task 10: fm_compile / fm_validate / fm_simulate end-to-end tool test

**Files:**
- Test: `AI4Science/tests/test_forward_model_tools.py` (add an end-to-end test)

The functions exist (Task 9); this task locks in their workspace behavior end-to-end.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_fm_compile_validate_simulate_end_to_end(tmp_path):
    import numpy as np
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}

    mask = np.random.default_rng(0).integers(0, 2, (8, 8)).astype(np.float64)
    model = from_modality("cassi", H=8, W=8, N_bands=4, mask=mask)
    dump_model_json(model, tmp_path, "forward_model_in.json")

    out = json.loads(tools["fm_compile"].func(str(tmp_path)))
    assert out["ok"] is True
    assert (tmp_path / "forward_model.json").exists()
    assert (tmp_path / "forward_model_report.json").exists()

    val = json.loads(tools["fm_validate"].func(str(tmp_path)))
    assert val["ok"] is True
    assert val["report"]["is_linear"] is True
    assert val["report"]["adjoint"]["passed"] is True

    sim = json.loads(tools["fm_simulate"].func(str(tmp_path)))
    assert sim["ok"] is True
    assert sim["y_shape"] == [8, 8]
    assert (tmp_path / "y.npy").exists()


def test_fm_compile_inline_model_json(tmp_path):
    tools = {t.name: t for t in forward_model_tools(gate_provider=None, workspace=tmp_path)}
    model_json = json.dumps({
        "name": "intensity", "x_shape": [4, 4],
        "stages": [{"op": "square_magnitude", "params": {}}],
    })
    out = json.loads(tools["fm_compile"].func(str(tmp_path), model=model_json))
    # nonlinear: compiles & validates, but flagged non-linear (adjoint skipped)
    assert "non-linear" in json.loads(
        (tmp_path / "forward_model_report.json").read_text())["warnings"][0]
```

- [ ] **Step 2: Run test to verify it fails (or passes)**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -k "end_to_end or inline" -v`
Expected: PASS if Task 9 was complete and correct. If it FAILS, fix the tool funcs in `forward_model_tools.py` until green (do not modify the test to match a bug).

- [ ] **Step 3: (only if red) fix implementation**

Adjust `_fm_compile` / `_fm_simulate` so the end-to-end test passes. No new files.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add AI4Science/tests/test_forward_model_tools.py AI4Science/ai4science/harness/forward_model_tools.py
git commit -m "test(forward-compiler): end-to-end fm_compile/validate/simulate tool flow"
```

---

## Task 11: Capability bundle "forward-model" + wire into agents

**Files:**
- Modify: `AI4Science/ai4science/harness/agents/capabilities.py`
- Modify: `AI4Science/ai4science/harness/agents/specs/computational_imaging.py`
- Modify: `AI4Science/ai4science/harness/agents/specs/research.py`
- Test: `AI4Science/tests/test_forward_model_tools.py` (add bundle-resolution test)

- [ ] **Step 1: Write the failing test (append)**

```python
def test_forward_model_capability_bundle_resolves():
    from ai4science.harness.agents.capabilities import resolve_capability, CAPABILITY_BUNDLES
    from ai4science.harness.agents.context import BuildContext

    assert "forward-model" in CAPABILITY_BUNDLES
    ctx = BuildContext(workspace=None, brand_provider=None)
    tools = resolve_capability("forward-model", ctx)
    names = {t.name for t in tools}
    assert {"fm_primitives", "fm_compile", "fm_validate", "fm_simulate"} <= names


def test_ci_and_research_specs_have_forward_model_capability():
    from ai4science.harness.agents.specs.computational_imaging import SPEC as CI_SPEC
    from ai4science.harness.agents.specs.research import SPEC as RESEARCH_SPEC
    assert "forward-model" in CI_SPEC.capabilities
    assert "forward-model" in RESEARCH_SPEC.capabilities
```

> Note: confirm the actual exported name in each spec module (it may be `SPEC`, `AGENT_SPEC`, or a builder fn). Inspect with `grep -nE "SPEC|AgentSpec\(|capabilities" ai4science/harness/agents/specs/computational_imaging.py` before writing, and match the test import to reality.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -k "capability or specs" -v`
Expected: FAIL — `"forward-model" not in CAPABILITY_BUNDLES`

- [ ] **Step 3: Write minimal implementation**

In `capabilities.py`, add a bundle provider (next to `_optics_design`):

```python
def _forward_model(ctx: BuildContext) -> List[Tool]:
    from ai4science.harness.forward_model_tools import forward_model_tools
    from ai4science.harness.pwm_gate import PwmGate
    return list(forward_model_tools(gate_provider=PwmGate.from_env,
                                    workspace=ctx.workspace))
```

And register it in `BUILTIN_BUNDLES`:

```python
    "forward-model": _forward_model,
```

In each agent spec, add `"forward-model"` to the `capabilities` tuple. For `computational_imaging.py`, locate the `capabilities=(...)` argument and append the string; e.g.:

```python
    capabilities=("pwm-data", "computational-imaging", "ci-algorithms",
                  "compute-providers", "optics-design", "forward-model"),
```

Do the same in `research.py` (append `"forward-model"` to its existing capabilities tuple). Match the exact existing entries — only add the new string, do not remove any.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add AI4Science/ai4science/harness/agents/capabilities.py AI4Science/ai4science/harness/agents/specs/computational_imaging.py AI4Science/ai4science/harness/agents/specs/research.py AI4Science/tests/test_forward_model_tools.py
git commit -m "feat(forward-compiler): forward-model capability bundle wired into CI + research agents"
```

---

## Task 12: Full-suite regression + integration smoke

**Files:**
- Test: run both suites; no new source unless a regression surfaces.

- [ ] **Step 1: Run the new compiler suite**

Run: `cd packages/pwm_core && python3 -m pytest tests/test_fc_*.py -v`
Expected: ALL PASS (ir/primitives/compiler/torch/validate/bridge/golden).

- [ ] **Step 2: Run the AI4Science tool suite**

Run: `cd AI4Science && python3 -m pytest tests/test_forward_model_tools.py -v`
Expected: ALL PASS.

- [ ] **Step 3: Run the agent-spec + capabilities regression**

Run: `cd AI4Science && python3 -m pytest tests/test_agents.py -v`
Expected: PASS — adding the capability must not break the moat invariants (open agents must still NOT receive `forward-model`). If `test_agents.py` asserts an explicit allowlist of science-tier capabilities, update that allowlist to include `"forward-model"`; if it asserts open agents have no PWM bundles, confirm `forward-model` is only on science-tier specs.

- [ ] **Step 4: Import smoke from a clean process**

Run:
```bash
cd /home/spiritai/pwm/Physics_World_Model && python3 -c "
from pwm_core.forward_compiler import compile_model, validate_forward_model
from pwm_core.forward_compiler.bridge import from_modality
m = from_modality('cassi', H=16, W=16, N_bands=8)
op = compile_model(m)
rep = validate_forward_model(m)
print('compiled', op.x_shape, '->', op.y_shape, '| ok', rep.ok, '| linear', rep.is_linear)
assert rep.ok and op.y_shape == (16, 16)
print('SMOKE OK')
"
```
Expected: prints `SMOKE OK`.

- [ ] **Step 5: Commit (if any regression fix was needed)**

```bash
git add -A
git commit -m "test(forward-compiler): full-suite regression + integration smoke green"
```

---

## Self-Review

**Spec coverage (vs `2026-06-19-ci-copilot-roadmap.md`, capability #2 "Forward-model compiler: NL/eqn/code → executable differentiable simulator, compile to pwm_core.physics"):**
- "executable simulator" → `CompiledOperator` (Tasks 4) + `fm_simulate` (Task 9/10). ✅
- "differentiable" → `as_torch()` autograd wrapper for linear models (Task 5). ✅
- "compile to pwm_core.physics" → `CompiledOperator(BaseOperator)` + golden fidelity vs `CASSIOperator` + GLOBAL_REGISTRY registration (Tasks 4, 8). ✅
- "identifiability / linearity / units check" (capability #1 overlap) → `validate_forward_model` (dims, adjoint, linearity classification, conditioning) (Task 6). ✅ (units check noted as a metadata field only — full unit-dimension analysis is deferred to a follow-on, see scope note below.)
- "NL/eqn/code → model" → boundary is the agent (tool docstrings instruct it to emit a structured `ForwardModel`); deterministic compiler validates/executes (Tasks 9–11). ✅
- PWM-metered moat tools on science-tier agents → `TOOL_PRICES` + `forward-model` bundle on CI + research only (Tasks 9, 11). ✅

**Deferred to follow-on plans (explicit, per roadmap Phase A "+ CI multi-agent skeleton" being a separate plan):** the Critic-led multi-agent skeleton; full physical-units dimensional analysis; additional modality templates beyond CASSI (MRI/CT/lensless — add via `from_modality` + new primitives); torch autograd for nonlinear stages (Phase B).

**Placeholder scan:** none — every code step contains complete, runnable code.

**Type consistency check:**
- `compile_model` (not `compile`, to avoid shadowing the builtin) used consistently across compiler.py, validate.py, bridge tests, tools, __init__ exports. ✅
- `ForwardModel.x_shape` is a tuple (coerced in `__post_init__`); `to_dict` emits a list; tests compare tuples after `from_dict`. ✅
- `Primitive` fields: `name, forward, out_shape, adjoint=None, is_linear=True` — used consistently. ✅
- `band_sum` adjoint requires `n_bands`, injected by `compile_model` from inferred shape; the unit test supplies it explicitly. ✅
- `ForwardModelReport.adjoint` is `Optional[AdjointCheckReport]`; `to_dict` guards `None`; tools read `report["adjoint"]["passed"]` only on linear models. ✅
- Tool funcs take `func(workspace: str, **args) -> str` returning JSON, matching the `Tool` dataclass contract. ✅

---

**Plan complete.**

"""DL4 -- expert projects, where the difficulty is scale rather than a trap.

The trap classes of :mod:`.traps` separate a careful implementation from a
careless one and separate no model: given a specification that names the hazard,
every executor read it. The measurement said what the remaining lever is, so
these classes use it. They are not trickier. They are **larger**: many rules
that interact, a long chain in which an early error propagates silently, and a
verification burden big enough that spot-checking does not substitute for
getting it right.

Nothing here is hidden from the agent. The specification states every rule it
will be judged on. What it does not state is which combinations the hidden cases
exercise, and there are more combinations than anyone checks by hand --- which is
the honest form of a T4 task: the work is not subtle, there is simply a great
deal of it and it all has to be consistent.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..spec import Difficulty, Loss
from ..verify import Verdict, missing, read_json
from .base import Generator

#: horizon 4, heavy coordination between rules, real ambiguity in the corners,
#: and a verification burden. Bands T4.
_T4 = Difficulty(horizon=4, coordination=4, uncertainty=3, ambiguity=3,
                 tooling=2, verification=3, novelty=2, change=0)


# ======================================================================
# A small language, specified completely and interacting everywhere
# ======================================================================

_LANG_SPEC_TEMPLATE = """\
# The `mini` expression language  (dialect @@DIALECT@@)

Implement `evaluate(source: str)` in `interp.py`. It takes one expression and
returns a Python value, or the string `"ERR"` if evaluation fails per the rules
below. It must never raise.

## Values

Integers (`0`, `-3`), booleans (`true`, `false`), strings (`"abc"`, double
quotes only, no escapes), and `null`.

## Operators, loosest binding first

| Precedence | Operators | Associativity |
|---|---|---|
| 1 (loosest) | `or` | left |
| 2 | `and` | left |
| 3 | `==`  `!=` | left |
| 4 | `<`  `<=`  `>`  `>=` | left |
| 5 | `+`  `-` | left |
| 6 | `*`  `/`  `%` | left |
| 7 (tightest) | unary `-`, unary `not` | right |

Parentheses group.

## Rules

1. **Short circuit.** `or` returns its left operand when that operand is truthy,
   without evaluating the right. `and` returns its left operand when that operand
   is falsy, without evaluating the right. Otherwise each returns its right
   operand. *These return the operand, not a boolean.*
2. **Truthiness.** `false`, `null`, `0` and `""` are falsy. Everything else is
   truthy, including negative numbers.
3. **Arithmetic** (`- * / %`) requires two integers, else `ERR`. `/` is integer
   division @@DIV_RULE@@. `%` returns the remainder consistent with that
   division, so `a % b` equals `a - b * (a / b)`. `/` or `%` by `0` is `ERR`.
4. **`+`** adds two integers, or concatenates two strings. Any other combination
   is `ERR`.
5. **Ordering** (`< <= > >=`) requires two integers or two strings; strings
   compare by Unicode code point. Any other combination is `ERR`.
6. **Equality** (`== !=`) is allowed between any two values and never errors.
   Values of different types are never equal. `null == null` is true.
7. **Unary `-`** requires an integer, else `ERR`. **Unary `not`** applies to any
   value and returns a boolean, the negation of its truthiness.
8. **`ERR` propagates.** If evaluating an operand yields `ERR`, the whole
   expression is `ERR` --- *except* where short circuit means the operand is never
   evaluated, in which case the error does not occur at all.
9. **`let NAME = expr in expr`** binds a name in the body only. An inner `let`
   of the same name shadows an outer one. A name that is not bound is `ERR`.
   `let` binds looser than every operator: `let x = 1 in x + 1` is `let x = 1 in
   (x + 1)`. The bound expression is evaluated **eagerly**, before the body, and
   rule 8 applies to it: if it yields `ERR` the whole `let` is `ERR`, *even when
   the name is never used*. `let` is not a short circuit.
10. **A syntax error is `ERR`.** So is an empty source.

## Deliverable

`interp.py` defining `evaluate(source)`. It will be imported and called directly.
"""


def _mini_eval(src: str, env: Optional[Dict[str, Any]] = None,
               dialect: Optional[Dict[str, str]] = None) -> Any:
    """The reference implementation, used only to build the hidden cases.

    Two rules vary per instance -- how integer division rounds, and whether
    comparing different types is false or an error -- because otherwise the
    staged workspace is byte-identical across seeds and one memorised
    interpreter answers every instance of the class. Both are stated in the
    specification the agent reads; what varies is the language, not what is
    disclosed about it.
    """
    dialect = dialect or {"div": "trunc", "eq": "false"}
    ERR = "ERR"
    toks: List[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j = src.find('"', i + 1)
            if j < 0:
                return ERR
            toks.append(src[i:j + 1])
            i = j + 1
            continue
        if c.isdigit():
            j = i
            while j < n and src[j].isdigit():
                j += 1
            toks.append(src[i:j])
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (src[j].isalnum() or src[j] == "_"):
                j += 1
            toks.append(src[i:j])
            i = j
            continue
        for two in ("==", "!=", "<=", ">="):
            if src.startswith(two, i):
                toks.append(two)
                i += 2
                break
        else:
            if c in "+-*/%<>()=":
                toks.append(c)
                i += 1
            else:
                return ERR
    if not toks:
        return ERR

    pos = 0

    def peek() -> Optional[str]:
        return toks[pos] if pos < len(toks) else None

    def eat(t: Optional[str] = None) -> str:
        nonlocal pos
        cur = toks[pos]
        pos += 1
        return cur

    class Bad(Exception):
        pass

    def truthy(v: Any) -> bool:
        return not (v is None or v is False or v == 0 and v is not True
                    or v == "" and isinstance(v, str))

    def expr(env: Dict[str, Any]) -> Any:
        if peek() == "let":
            eat()
            if peek() is None or not (peek()[0].isalpha() or peek()[0] == "_"):
                raise Bad()
            name = eat()
            if peek() != "=":
                raise Bad()
            eat()
            val = expr(env)
            if peek() != "in":
                raise Bad()
            eat()
            inner = dict(env)
            inner[name] = val
            body = expr(inner)
            # Eager binding, rule 9: an ERR in the bound expression
            # propagates even when the name is never used. The spec did not
            # say so until a model answered the other way and was marked
            # wrong for a reading its text permitted.
            return "ERR" if val == "ERR" else body
        return or_(env)

    def _binary(sub, ops, env, apply):
        left = sub(env)
        while peek() in ops:
            op = eat()
            right = sub(env)
            left = apply(op, left, right)
        return left

    def or_(env):
        left = and_(env)
        while peek() == "or":
            eat()
            if left != "ERR" and truthy(left):
                # short circuit: parse and discard the right operand
                depth_start = pos
                and_(env)
                continue
            right = and_(env)
            left = right if left != "ERR" else "ERR"
        return left

    def and_(env):
        left = eq(env)
        while peek() == "and":
            eat()
            if left != "ERR" and not truthy(left):
                eq(env)
                continue
            right = eq(env)
            left = right if left != "ERR" else "ERR"
        return left

    def eq(env):
        def apply(op, a, b):
            if a == "ERR" or b == "ERR":
                return "ERR"
            if type(a) is not type(b) and dialect["eq"] == "err":
                return "ERR"
            same = type(a) is type(b) and a == b
            return same if op == "==" else not same
        return _binary(cmp_, ("==", "!="), env, apply)

    def cmp_(env):
        def apply(op, a, b):
            if a == "ERR" or b == "ERR":
                return "ERR"
            ok = ((isinstance(a, int) and not isinstance(a, bool)
                   and isinstance(b, int) and not isinstance(b, bool))
                  or (isinstance(a, str) and isinstance(b, str)))
            if not ok:
                return "ERR"
            return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
        return _binary(add, ("<", "<=", ">", ">="), env, apply)

    def _is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    def add(env):
        def apply(op, a, b):
            if a == "ERR" or b == "ERR":
                return "ERR"
            if op == "+":
                if _is_int(a) and _is_int(b):
                    return a + b
                if isinstance(a, str) and isinstance(b, str):
                    return a + b
                return "ERR"
            return a - b if _is_int(a) and _is_int(b) else "ERR"
        return _binary(mul, ("+", "-"), env, apply)

    def mul(env):
        def apply(op, a, b):
            if a == "ERR" or b == "ERR":
                return "ERR"
            if not (_is_int(a) and _is_int(b)):
                return "ERR"
            if op in ("/", "%") and b == 0:
                return "ERR"
            if op == "*":
                return a * b
            if dialect["div"] == "floor":
                q = a // b
            else:
                mag = abs(a) // abs(b)
                q = mag if (a >= 0) == (b >= 0) else -mag
            return q if op == "/" else a - b * q
        return _binary(unary, ("*", "/", "%"), env, apply)

    def unary(env):
        if peek() == "-":
            eat()
            v = unary(env)
            if v == "ERR":
                return "ERR"
            return -v if _is_int(v) else "ERR"
        if peek() == "not":
            eat()
            v = unary(env)
            return "ERR" if v == "ERR" else (not truthy(v))
        return atom(env)

    def atom(env):
        t = peek()
        if t is None:
            raise Bad()
        if t == "(":
            eat()
            v = expr(env)
            if peek() != ")":
                raise Bad()
            eat()
            return v
        eat()
        if t.isdigit():
            return int(t)
        if t.startswith('"'):
            return t[1:-1]
        if t == "true":
            return True
        if t == "false":
            return False
        if t == "null":
            return None
        if t in ("let", "in", "and", "or", "not"):
            raise Bad()
        return env[t] if t in env else "ERR"

    try:
        v = expr(dict(env or {}))
        if pos != len(toks):
            return "ERR"
        return v
    except Bad:
        return "ERR"
    except Exception:
        return "ERR"


def _gen_expr(rng: random.Random, depth: int = 0) -> str:
    """A random source string, biased toward the rule interactions."""
    atoms = ['1', '2', '7', '0', '-3', 'true', 'false', 'null', '"a"', '"bc"', '""']
    if depth >= 3 or rng.random() < 0.3:
        return rng.choice(atoms)
    r = rng.random()
    a = _gen_expr(rng, depth + 1)
    b = _gen_expr(rng, depth + 1)
    if r < 0.12:
        return "let x = %s in %s" % (a, rng.choice([b, "x + 1", "x", "x and %s" % b]))
    if r < 0.24:
        return "not %s" % a
    if r < 0.30:
        return "-%s" % a
    if r < 0.40:
        return "(%s)" % a
    op = rng.choice(["or", "and", "==", "!=", "<", "<=", ">", ">=",
                     "+", "-", "*", "/", "%"])
    return "%s %s %s" % (a, op, b)


_CASE_RUNNER = '''\
import importlib.util, json, sys

spec = importlib.util.spec_from_file_location("interp", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cases = json.load(open(sys.argv[2]))
wrong, crashed = [], []
for c in cases:
    try:
        got = m.evaluate(c["src"])
    except Exception as e:
        crashed.append({"src": c["src"], "error": "%s: %s" % (type(e).__name__, e)})
        continue
    if got != c["want"] or type(got) is not type(c["want"]):
        wrong.append({"src": c["src"], "want": c["want"], "got": repr(got)})
json.dump({"total": len(cases), "wrong": wrong, "crashed": crashed},
          open(sys.argv[3], "w"))
'''


DIALECTS = (
    {"div": "trunc", "eq": "false",
     "div_rule": "truncating toward zero, so `-7 / 2` is `-3`",
     "eq_rule": ("is allowed between any two values and never errors. Values of "
                 "different types are never equal."),
     "dialect": "A"},
    {"div": "floor", "eq": "false",
     "div_rule": "flooring toward negative infinity, so `-7 / 2` is `-4`",
     "eq_rule": ("is allowed between any two values and never errors. Values of "
                 "different types are never equal."),
     "dialect": "B"},
    {"div": "trunc", "eq": "err",
     "div_rule": "truncating toward zero, so `-7 / 2` is `-3`",
     "eq_rule": ("requires both operands to have the same type; comparing "
                 "different types is `ERR`."),
     "dialect": "C"},
    {"div": "floor", "eq": "err",
     "div_rule": "flooring toward negative infinity, so `-7 / 2` is `-4`",
     "eq_rule": ("requires both operands to have the same type; comparing "
                 "different types is `ERR`."),
     "dialect": "D"},
)


def _b_lang(work: Path, keyed: Path, rng: random.Random) -> None:
    dialect = dict(rng.choice(DIALECTS))
    spec_text = _LANG_SPEC_TEMPLATE
    for token, field in (("@@DIV_RULE@@", "div_rule"), ("@@EQ_RULE@@", "eq_rule"),
                         ("@@DIALECT@@", "dialect")):
        spec_text = spec_text.replace(token, dialect[field])
    (work / "SPEC.md").write_text(spec_text, encoding="utf-8")
    (work / "interp.py").write_text(
        '"""Implement evaluate() per SPEC.md."""\n\n\n'
        "def evaluate(source):\n"
        '    raise NotImplementedError("see SPEC.md")\n', encoding="utf-8")

    # A handful of visible examples, so the shape of the answer is unambiguous.
    fixed = ['1 + 2 * 3', '"a" + "b"', '1 + "a"', '3 / 0', 'let x = 2 in x * x',
             'false or 7', '0 or "z"', 'not 0', '-7 / 2', '1 == true']
    extra = []
    while len(extra) < 6:
        e = _gen_expr(rng)
        if e not in fixed and e not in extra:
            extra.append(e)
    (work / "examples.json").write_text(json.dumps(
        [{"src": x, "want": _mini_eval(x, dialect=dialect)} for x in fixed + extra],
        indent=2), encoding="utf-8")

    # The hidden set: many more, generated per seed so it cannot be memorised.
    seen, cases = set(), []
    while len(cases) < 220:
        src = _gen_expr(rng)
        if src in seen:
            continue
        seen.add(src)
        cases.append({"src": src, "want": _mini_eval(src, dialect=dialect)})
    # Guarantee coverage of every rule that a partial implementation skips.
    for src in ('let x = 1 in let x = 2 in x', 'let y = 1 in z',
                '"b" < "a"', 'null == null', 'null == false', '1 == "1"',
                '7 % 0', '-7 / 2', '7 / -2', '-7 % 2',
                'true and 0 or "k"', 'false and (1/0)', 'true or (1/0)',
                'not not 5', '(1', '', '1 +', 'let x = 1 in x + 1'):
        cases.append({"src": src, "want": _mini_eval(src, dialect=dialect)})
    (keyed / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
    (keyed / "dialect.json").write_text(json.dumps(dialect, sort_keys=True),
                                        encoding="utf-8")
    (keyed / "runner.py").write_text(_CASE_RUNNER, encoding="utf-8")


def _v_lang(work: Path, keyed: Path) -> Verdict:
    note = ("%d hidden expressions, generated per seed from the same grammar as "
            "the visible examples, plus a fixed set covering every rule a "
            "partial implementation tends to skip. Every case must match in "
            "value AND type, and evaluate() must never raise. The spec is "
            "complete and visible; what is hidden is only which combinations "
            "are exercised")
    if missing(work, "interp.py"):
        return Verdict(False, {}, ("interp.py is gone",), note % 0, 0.0)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out = td / "res.json"
        py = sys.executable if not getattr(sys, "frozen", False) else (
            shutil.which("python3") or shutil.which("python") or sys.executable)
        try:
            r = subprocess.run(
                [py, str(keyed / "runner.py"), str(work / "interp.py"),
                 str(keyed / "cases.json"), str(out)],
                capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return Verdict(False, {}, ("the case runner timed out",), note % 0, 0.0)
        if r.returncode != 0:
            return Verdict(False, {},
                           ("interp.py could not be imported or run: %s"
                            % (r.stderr or "")[-300:],), note % 0, 0.0)
        res = json.loads(out.read_text())

    total = res["total"]
    wrong, crashed = res["wrong"], res["crashed"]
    reasons = []
    if crashed:
        reasons.append("evaluate() raised on %d case(s); it must return \"ERR\" "
                       "instead. First: %s" % (len(crashed), crashed[0]["src"][:40]))
    if wrong:
        ex = wrong[0]
        reasons.append("%d of %d cases wrong. First: %r -> want %r, got %s"
                       % (len(wrong), total, ex["src"][:40], ex["want"], ex["got"]))
    return Verdict(not reasons,
                   {"cases": float(total),
                    "correct": float(total - len(wrong) - len(crashed)),
                    "accuracy": (total - len(wrong) - len(crashed)) / max(1, total)},
                   tuple(reasons), note % total, 0.0)


mini_language = Generator(
    key="t4.mini_language", family="software", level="DL4",
    difficulty=_T4, loss=Loss(value=1.0, c_detect=0.4, c_undo=0.3),
    prompt="Read SPEC.md and implement what it describes in interp.py.",
    deliverables=("interp.py",),
    verifier_note=("~240 hidden expressions per seed; every one must match in "
                   "value and type, and evaluate() must never raise"),
    build=_b_lang, verify=_v_lang,
)

ALL = (mini_language,)

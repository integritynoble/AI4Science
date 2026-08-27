"""Known-good solutions, used to prove the verifiers open as well as close.

A benchmark that has only ever been run against nothing has been shown to
refuse, which is the easy half. These solvers do each task correctly, so the
suite can assert that a correct answer *passes* -- and each has a paired wrong
answer, so it can assert that a plausible-but-wrong one does not.

They are test material and are never staged into a run. Two of them
(``t5.hidden_law``, and the wrong-answer variants) read the withheld key on
purpose: they are oracles for testing the harness, not solvers, and the
distinction is the whole point of the directory split.
"""
from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Callable, Dict

from .verify import read_json


# ---------------------------------------------------------------- DL0

def r_csv_to_json(work: Path, keyed: Path) -> None:
    with (work / "data.csv").open(encoding="utf-8", newline="") as fh:
        rows = [{"city": r["city"], "count": int(r["count"]), "score": float(r["score"])}
                for r in csv.DictReader(fh)]
    (work / "out.json").write_text(json.dumps(rows, indent=2, sort_keys=True),
                                   encoding="utf-8")


def r_change_constant(work: Path, keyed: Path) -> None:
    want = int(re.search(r"RATE in calc\.py to (\d+)",
                         (work / "TASK.txt").read_text(encoding="utf-8")).group(1))
    p = work / "calc.py"
    p.write_text(re.sub(r"^RATE = \d+", "RATE = %d" % want,
                        p.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")


def r_rename_file(work: Path, keyed: Path) -> None:
    m = re.search(r"Rename (\S+) to (\S+)\.", (work / "TASK.txt").read_text(encoding="utf-8"))
    (work / m.group(1)).rename(work / m.group(2))


def r_extract_fields(work: Path, keyed: Path) -> None:
    t = (work / "report.txt").read_text(encoding="utf-8")
    ref = re.search(r"reference for this note is\s+(REF-\d+)", t).group(1)
    amount = float(re.search(r"Settlement of ([\d.]+) is due", t).group(1))
    due = re.search(r"due on\s+(\d{4}-\d{2}-\d{2})", t).group(1)
    (work / "fields.json").write_text(
        json.dumps({"reference": ref, "amount": amount, "due": due}, sort_keys=True),
        encoding="utf-8")


def r_compute_median(work: Path, keyed: Path) -> None:
    xs = sorted(float(x) for x in (work / "series.txt").read_text().split())
    n = len(xs)
    med = xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    (work / "answer.txt").write_text("%r\n" % med, encoding="utf-8")


# ---------------------------------------------------------------- DL1

def _timeout_pkg(work: Path) -> Path:
    for d in work.iterdir():
        if d.is_dir() and (d / "http.py").exists():
            return d
    raise AssertionError("no package with http.py")


def r_request_timeout(work: Path, keyed: Path) -> None:
    want = int(re.search(r"wait (\d+) seconds",
                         (work / "GOAL.md").read_text(encoding="utf-8")).group(1))
    p = _timeout_pkg(work) / "http.py"
    p.write_text(re.sub(r"^REQUEST_TIMEOUT = \d+", "REQUEST_TIMEOUT = %d" % want,
                        p.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")


def r_clean_dataset(work: Path, keyed: Path) -> None:
    with (work / "raw.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    last: Dict[str, int] = {}
    for i, r in enumerate(rows):
        if r["name"]:
            last[r["id"]] = i
    out = []
    for i, r in enumerate(rows):
        if r["name"] and last[r["id"]] == i:
            d, m, y = r["date"].split("/")
            out.append({"id": r["id"], "name": r["name"], "date": "%s-%s-%s" % (y, m, d)})
    with (work / "cleaned.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "name", "date"])
        w.writeheader()
        w.writerows(out)


def r_bounded_answer(work: Path, keyed: Path) -> None:
    q = (work / "QUESTION.txt").read_text(encoding="utf-8")
    site = re.search(r"cost for (\w+)\?", q).group(1)
    inv = (work / "sources" / "a_inventory.md").read_text(encoding="utf-8")
    units = int(re.search(r"\|\s*%s\s*\|\s*(\d+)\s*\|" % site, inv).group(1))
    rates = (work / "sources" / "b_rates.md").read_text(encoding="utf-8")
    rate = int(re.search(r"rate is\s+(\d+) per unit", rates).group(1))
    (work / "answer.txt").write_text("%d\n" % (rate * units), encoding="utf-8")


# ---------------------------------------------------------------- DL2

_INI_LOADER = '''\
"""Configuration loading."""
import json


class ConfigError(ValueError):
    """Raised when a configuration file cannot be understood."""


def _load_ini(text):
    out, section = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" not in line:
            raise ConfigError("malformed line, no '=': %r" % raw)
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        out[("%s.%s" % (section, k)) if section else k] = str(v)
    return out


def load(path):
    """Load a configuration file and return a dict of str -> str."""
    text = open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ConfigError("top level must be an object")
        return {str(k): str(v) for k, v in data.items()}
    if path.endswith(".ini"):
        return _load_ini(text)
    raise ConfigError("unsupported configuration format: %s" % path)
'''


def r_config_format(work: Path, keyed: Path) -> None:
    (work / "conf" / "loader.py").write_text(_INI_LOADER, encoding="utf-8")
    rd = work / "README.md"
    rd.write_text(rd.read_text(encoding="utf-8").rstrip("\n")
                  + "\n- INI (`.ini`) -- sections become key prefixes\n",
                  encoding="utf-8")
    (work / "tests" / "test_loader.py").write_text(
        "import os\nfrom conf.loader import load\n\n"
        "FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fixtures')\n\n\n"
        "def test_json():\n"
        "    assert load(os.path.join(FIX, 'old.json'))['port'] == '8080'\n\n\n"
        "def test_ini():\n"
        "    assert load(os.path.join(FIX, 'new.ini'))['server.host'] == 'example.org'\n",
        encoding="utf-8")


def r_pipeline(work: Path, keyed: Path) -> None:
    import datetime
    totals: Dict[str, float] = {}
    rejected = 0
    with (work / "sales.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                amt = float(r["amount"])
                datetime.date.fromisoformat(r["date"])
            except (ValueError, TypeError):
                rejected += 1
                continue
            totals[r["region"]] = totals.get(r["region"], 0.0) + amt
    (work / "report.json").write_text(json.dumps(
        {"totals": {k: round(v, 2) for k, v in totals.items()},
         "rejected": rejected,
         "top_region": max(totals, key=lambda k: totals[k])}, sort_keys=True),
        encoding="utf-8")


# ---------------------------------------------------------------- DL3

_FAST_SEARCH = '''\
"""In-memory search over a small document set."""


def _tokenise(text):
    return [t for t in text.lower().replace(",", " ").replace(".", " ").split() if t]


def build_index(documents):
    """Return the structure `search` reads: a set of tokens per document."""
    return [(i, frozenset(_tokenise(d))) for i, d in enumerate(documents)]


def search(index, query, limit=5):
    """Return up to `limit` document ids matching every term in `query`."""
    terms = frozenset(_tokenise(query))
    hits, seen = [], set()
    for doc_id, tokens in index:
        if terms <= tokens and doc_id not in seen:
            seen.add(doc_id)
            hits.append(doc_id)
            if len(hits) >= limit:
                break
    return hits
'''


def r_search_latency(work: Path, keyed: Path) -> None:
    (work / "search.py").write_text(_FAST_SEARCH, encoding="utf-8")


# ---------------------------------------------------------------- DL5

def r_hidden_law(work: Path, keyed: Path) -> None:
    """ORACLE, not a solver. Reads the key to produce the exact answer.

    Its only job is to prove the verifier passes a correct discovery. A real
    attempt never sees ``keyed/``.
    """
    truth = read_json(keyed / "truth.json")
    (work / "predictions.json").write_text(json.dumps(truth["y"]), encoding="utf-8")
    (work / "mechanism.txt").write_text(
        "family=%s params=%s\n" % (truth["kind"], truth["params"]), encoding="utf-8")


def w_hidden_law(work: Path, keyed: Path) -> None:
    """The plausible wrong answer: nearest neighbour from the observations.

    It fits the measured range well and cannot leave it, which is exactly the
    behaviour the extrapolation grid is there to catch.
    """
    obs = read_json(work / "observations.json")
    grid = read_json(work / "predict_at.json")
    preds = []
    for g in grid:
        best, bd = 0.0, None
        for t in obs:
            d = (t["a"] - g["a"]) ** 2 + (t["b"] - g["b"]) ** 2
            if bd is None or d < bd:
                bd, best = d, t["y"]
        preds.append(best)
    (work / "predictions.json").write_text(json.dumps(preds), encoding="utf-8")
    (work / "mechanism.txt").write_text("it looks smooth\n", encoding="utf-8")


# -- wrong answers that a careless attempt would actually produce ----------

def w_clean_dataset(work: Path, keyed: Path) -> None:
    """First-wins dedup and a US date read: both traps, taken."""
    with (work / "raw.csv").open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    seen, out = set(), []
    for r in rows:
        if not r["name"] or r["id"] in seen:
            continue
        seen.add(r["id"])
        m, d, y = r["date"].split("/")
        out.append({"id": r["id"], "name": r["name"], "date": "%s-%s-%s" % (y, m, d)})
    with (work / "cleaned.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "name", "date"])
        w.writeheader()
        w.writerows(out)


def w_extract_fields(work: Path, keyed: Path) -> None:
    """First REF- match in the file, which the appendix decoys do not change --
    but the amount is read as an integer, losing the cents."""
    t = (work / "report.txt").read_text(encoding="utf-8")
    ref = re.search(r"(REF-\d+)", t).group(1)
    amount = int(float(re.search(r"Settlement of ([\d.]+)", t).group(1)))
    due = re.search(r"(\d{4}-\d{2}-\d{2})", t).group(1)
    (work / "fields.json").write_text(json.dumps(
        {"reference": ref, "amount": amount, "due": due}, sort_keys=True), encoding="utf-8")


def w_request_timeout(work: Path, keyed: Path) -> None:
    """Global search and replace of the current value, which hits the neighbours."""
    g = (work / "GOAL.md").read_text(encoding="utf-8")
    want = int(re.search(r"wait (\d+) seconds", g).group(1))
    now = int(re.search(r"current (\d+)", g).group(1))
    pkg = _timeout_pkg(work)
    for name in ("http.py", "cache.py", "retry.py"):
        p = pkg / name
        p.write_text(p.read_text(encoding="utf-8").replace("= %d" % now, "= %d" % want),
                     encoding="utf-8")


def w_pipeline(work: Path, keyed: Path) -> None:
    """Coerces bad rows to zero instead of rejecting them: totals survive, the
    rejected count does not."""
    totals: Dict[str, float] = {}
    with (work / "sales.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                amt = float(r["amount"])
            except ValueError:
                amt = 0.0
            totals[r["region"]] = totals.get(r["region"], 0.0) + amt
    (work / "report.json").write_text(json.dumps(
        {"totals": {k: round(v, 2) for k, v in totals.items()}, "rejected": 0,
         "top_region": max(totals, key=lambda k: totals[k])}, sort_keys=True),
        encoding="utf-8")


def w_search_latency(work: Path, keyed: Path) -> None:
    """Leaves the code alone. Correct results, no speedup."""
    return None



# ---------------------------------------------------- DL3 trap classes

def r_causal_order(work: Path, keyed: Path) -> None:
    """Follow the parent chain, which is what the spec asks for."""
    ops = [json.loads(l) for l in
           (work / "ops.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by_parent = {o["parent"]: o for o in ops}
    state: Dict[str, int] = {}
    cur = None
    while cur in by_parent:
        o = by_parent[cur]
        if o["op"] == "set":
            state[o["field"]] = o["value"]
        else:
            state[o["field"]] = state.get(o["field"], 0) + o["value"]
        cur = o["id"]
    (work / "state.json").write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def w_causal_order(work: Path, keyed: Path) -> None:
    """Sort by timestamp: the reflex, and wrong when the clocks disagree."""
    ops = [json.loads(l) for l in
           (work / "ops.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    state: Dict[str, int] = {}
    for o in sorted(ops, key=lambda x: x["timestamp"]):
        if o["op"] == "set":
            state[o["field"]] = o["value"]
        else:
            state[o["field"]] = state.get(o["field"], 0) + o["value"]
    (work / "state.json").write_text(json.dumps(state, sort_keys=True), encoding="utf-8")


def r_dst_daily_totals(work: Path, keyed: Path) -> None:
    """Convert into the named zone before taking the date."""
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Berlin")
    tot: Dict[str, float] = {}
    with (work / "events.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            u = datetime.strptime(r["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc)
            d = u.astimezone(tz).date().isoformat()
            tot[d] = round(tot.get(d, 0.0) + float(r["amount"]), 2)
    (work / "totals.json").write_text(json.dumps(tot, sort_keys=True), encoding="utf-8")


def w_dst_daily_totals(work: Path, keyed: Path) -> None:
    """Slice the date off the UTC string; misfiles everything near local midnight."""
    tot: Dict[str, float] = {}
    with (work / "events.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = r["timestamp_utc"][:10]
            tot[d] = round(tot.get(d, 0.0) + float(r["amount"]), 2)
    (work / "totals.json").write_text(json.dumps(tot, sort_keys=True), encoding="utf-8")


_ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\ufeff")


def _fold(s: str) -> str:
    import unicodedata
    s = "".join(ch for ch in s if ch not in _ZERO_WIDTH)
    return unicodedata.normalize("NFKC", s)


def r_unicode_identity(work: Path, keyed: Path) -> None:
    """Compare folded; keep the first occurrence's original spelling."""
    seen, out = set(), []
    with (work / "ids.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            f = _fold(r["identifier"])
            if f in seen:
                continue
            seen.add(f)
            out.append({"identifier": r["identifier"], "label": r["label"]})
    (work / "unique.json").write_text(json.dumps(out, ensure_ascii=False),
                                      encoding="utf-8")


def w_unicode_identity(work: Path, keyed: Path) -> None:
    """Byte-exact comparison; keeps rows that render identically."""
    seen, out = set(), []
    with (work / "ids.csv").open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["identifier"] in seen:
                continue
            seen.add(r["identifier"])
            out.append({"identifier": r["identifier"], "label": r["label"]})
    (work / "unique.json").write_text(json.dumps(out, ensure_ascii=False),
                                      encoding="utf-8")


# ---------------------------------------------------- DL4 expert projects

def r_mini_language(work: Path, keyed: Path) -> None:
    """A correct interpreter: the module's own reference, written out.

    An ORACLE for the harness, not a solver -- it is the same code that produced
    the expected values, so it proves the runner works and proves nothing about
    the task's difficulty. The partial implementation below is the informative
    one.
    """
    import inspect
    import json as _json
    from . import reference as _self          # noqa: F401  (path anchor)
    from .tasks import expert
    src = inspect.getsource(expert._mini_eval)
    # The dialect varies per instance, so the oracle reads it rather than
    # assuming the default -- an oracle that hard-coded one dialect would fail
    # three instances in four and look like a broken task.
    dialect = _json.loads((keyed / "dialect.json").read_text(encoding="utf-8"))
    (work / "interp.py").write_text(
        "from typing import Any, Dict, List, Optional\n\n"
        "DIALECT = %r\n\n" % ({"div": dialect["div"], "eq": dialect["eq"]},)
        + src.replace("def _mini_eval(", "def _run(")
        + "\n\ndef evaluate(source):\n    return _run(source, dialect=DIALECT)\n",
        encoding="utf-8")


_PARTIAL_INTERP = """\
\"\"\"A plausible partial reading of SPEC.md.

It gets the common cases right and skips three rules that only show up in
combination: `and`/`or` return a BOOLEAN rather than the operand, integer
division floors instead of truncating toward zero, and equality coerces across
types the way Python does. Each is the reading someone writes when they have
skimmed the spec rather than held all of it at once.
\"\"\"


def evaluate(source):
    try:
        return _ev(source)
    except Exception:
        return "ERR"


def _ev(src):
    import ast
    src = src.strip()
    if not src:
        return "ERR"
    py = (src.replace(" and ", " and ").replace(" or ", " or ")
             .replace("true", "True").replace("false", "False")
             .replace("null", "None").replace("not ", "not "))
    try:
        node = ast.parse(py, mode="eval")
    except SyntaxError:
        return "ERR"
    try:
        v = eval(compile(node, "<mini>", "eval"), {"__builtins__": {}}, {})
    except ZeroDivisionError:
        return "ERR"
    except Exception:
        return "ERR"
    if isinstance(v, float):
        v = int(v)
    return v
"""


def w_mini_language(work: Path, keyed: Path) -> None:
    (work / "interp.py").write_text(_PARTIAL_INTERP, encoding="utf-8")

def r_shift_schedule(work: Path, keyed: Path) -> None:
    """The exact optimiser, written out from the module that built the key.

    Like the interpreter oracle this proves the runner works, not that the task
    is easy. The greedy below is the informative one: it is feasible every
    time and still fails most instances, which is exactly the failure mode the
    class exists to detect.
    """
    import inspect
    import json as _json
    from .tasks import expert
    variant = _json.loads((keyed / "variant.json").read_text(encoding="utf-8"))
    (work / "solve.py").write_text(
        "REUSE = %r\n\n" % (variant["reuse"],)
        + inspect.getsource(expert._sched_optimum).replace(
            "def _sched_optimum(", "def _optimum(")
        + "\n\n" + _EXACT_SELECTION,
        encoding="utf-8")


#: The optimum cost is not an answer -- the task asks for a selection. This
#: recovers one by re-walking the same states and taking any pattern that lies
#: on a cheapest path.
_EXACT_SELECTION = """\
def solve(days, patterns):
    target = _optimum(days, patterns, REUSE)
    dem = tuple(days)
    goal = dem
    start = tuple([0] * len(days))

    def apply(state, pat):
        s = list(state)
        for d in pat["days"]:
            if s[d] < dem[d]:
                s[d] += 1
        return tuple(s)

    # Depth-first over states, pruned by the exact cost-to-go, so the first
    # complete path found is optimal.
    best_rest = {}

    def rest(state, allowed):
        key = (state, allowed)
        if key not in best_rest:
            sub = [patterns[i] for i in sorted(allowed)] if not REUSE else patterns
            need = [max(0, dem[i] - state[i]) for i in range(len(days))]
            best_rest[key] = _optimum(need, [
                {"days": [d for d in p["days"] if need[d] > 0], "cost": p["cost"]}
                for p in sub], REUSE)
        return best_rest[key]

    chosen, state = [], start
    allowed = frozenset(range(len(patterns)))
    spent = 0
    while state != goal:
        for i in sorted(allowed):
            p = patterns[i]
            nxt = apply(state, p)
            if nxt == state:
                continue
            nxt_allowed = allowed if REUSE else allowed - {i}
            r = rest(nxt, nxt_allowed)
            if r is not None and spent + p["cost"] + r == target:
                chosen.append(i)
                spent += p["cost"]
                state = nxt
                allowed = nxt_allowed
                break
        else:                                  # pragma: no cover - unreachable
            raise RuntimeError("no pattern lies on a cheapest path")
    return chosen
"""


_GREEDY_SOLVE = """\
\"\"\"A plausible reading of SPEC.md that optimises locally.

Take the pattern with the lowest cost per still-needed day, repeat until every
day is covered. Always feasible when a feasible selection exists, and not
always minimal -- which the visible examples are too few to reveal.
\"\"\"

REUSE = %r


def solve(days, patterns):
    need = list(days)
    used = []
    while any(need):
        best, best_ratio = None, None
        for i, p in enumerate(patterns):
            if not REUSE and i in used:
                continue
            gain = sum(1 for d in p["days"] if need[d] > 0)
            if not gain:
                continue
            ratio = p["cost"] / gain
            if best_ratio is None or ratio < best_ratio:
                best, best_ratio = i, ratio
        if best is None:
            return used
        used.append(best)
        for d in patterns[best]["days"]:
            if need[d] > 0:
                need[d] -= 1
    return used
"""


def w_shift_schedule(work: Path, keyed: Path) -> None:
    import json as _json
    variant = _json.loads((keyed / "variant.json").read_text(encoding="utf-8"))
    (work / "solve.py").write_text(_GREEDY_SOLVE % (variant["reuse"],),
                                   encoding="utf-8")


#: generator key -> (correct solver, wrong-but-plausible solver or None)
SOLVERS: Dict[str, Callable[[Path, Path], None]] = {
    "t0.csv_to_json": r_csv_to_json,
    "t0.change_constant": r_change_constant,
    "t0.rename_file": r_rename_file,
    "t0.extract_fields": r_extract_fields,
    "t0.compute_median": r_compute_median,
    "t1.request_timeout": r_request_timeout,
    "t1.clean_dataset": r_clean_dataset,
    "t1.bounded_answer": r_bounded_answer,
    "t2.config_format": r_config_format,
    "t2.pipeline": r_pipeline,
    "t3.search_latency": r_search_latency,
    "t5.hidden_law": r_hidden_law,
    "t3.causal_order": r_causal_order,
    "t3.dst_daily_totals": r_dst_daily_totals,
    "t3.unicode_identity": r_unicode_identity,
    "t4.mini_language": r_mini_language,
    "t4.shift_schedule": r_shift_schedule,
}

WRONG: Dict[str, Callable[[Path, Path], None]] = {
    "t0.extract_fields": w_extract_fields,
    "t1.clean_dataset": w_clean_dataset,
    "t1.request_timeout": w_request_timeout,
    "t2.pipeline": w_pipeline,
    "t3.search_latency": w_search_latency,
    "t5.hidden_law": w_hidden_law,
    "t3.causal_order": w_causal_order,
    "t3.dst_daily_totals": w_dst_daily_totals,
    "t3.unicode_identity": w_unicode_identity,
    "t4.mini_language": w_mini_language,
    "t4.shift_schedule": w_shift_schedule,
}

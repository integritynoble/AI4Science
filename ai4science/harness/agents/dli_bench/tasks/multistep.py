"""DL2 -- multi-step delegation, and DL3 -- outcome to strategy.

DL2 is where delegation starts to be worth anything. The human states a task;
the agent builds and holds the plan. Every task here has at least five
dependent operations, at least one intermediate result that must survive, at
least one recoverable failure planted in the inputs, and an external check.

DL3 removes the task and leaves the outcome. The human says what must be true
at the end and what may not be broken getting there, and says nothing about
where the problem is. A T3 instance therefore plants a cause the agent has to
find, and a constraint that rules out the obvious shortcut.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

from ..spec import Difficulty, Loss
from ..verify import Verdict, missing, read_json, run_hidden_tests
from .base import Generator


# -- DL2: add a format to a loader, without breaking the old one -----------

_LOADER = '''\
"""Configuration loading."""
import json


class ConfigError(ValueError):
    """Raised when a configuration file cannot be understood."""


def load(path):
    """Load a configuration file and return a dict of str -> str."""
    text = open(path, encoding="utf-8").read()
    if path.endswith(".json"):
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ConfigError("top level must be an object")
        return {str(k): str(v) for k, v in data.items()}
    raise ConfigError("unsupported configuration format: %s" % path)
'''

_HIDDEN_TESTS = """\
import os
import pytest

from conf.loader import load, ConfigError

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")


def test_json_still_works():
    \"\"\"Backward compatibility. The old format must not regress.\"\"\"
    assert load(os.path.join(FIX, "old.json")) == {"%(jk1)s": "%(jv1)s", "%(jk2)s": "%(jv2)s"}


def test_ini_sections_are_flattened():
    got = load(os.path.join(FIX, "new.ini"))
    assert got["%(s1)s.%(k1)s"] == "%(v1)s"
    assert got["%(s1)s.%(k2)s"] == "%(v2)s"
    assert got["%(s2)s.%(k3)s"] == "%(v3)s"


def test_ini_values_are_strings():
    got = load(os.path.join(FIX, "new.ini"))
    assert all(isinstance(v, str) for v in got.values())


def test_comments_and_blank_lines_ignored():
    got = load(os.path.join(FIX, "new.ini"))
    assert not any(k.startswith("#") or k.startswith(";") for k in got)
    assert len(got) == 3


def test_malformed_raises_configerror_not_something_else():
    \"\"\"The planted failure. A line with no '=' inside a section is malformed.

    It must raise ConfigError -- the module's own error -- rather than an
    IndexError or a ValueError from str.split, because a caller catches
    ConfigError and cannot catch what it has not been told about.
    \"\"\"
    with pytest.raises(ConfigError):
        load(os.path.join(FIX, "broken.ini"))


def test_unknown_extension_still_refused():
    with pytest.raises(ConfigError):
        load(os.path.join(FIX, "mystery.%(ext)s"))
"""


def _b_config(work: Path, keyed: Path, rng: random.Random) -> None:
    # Sections, keys, values and the unknown extension all move with the seed,
    # and the hidden suite is generated to match. Otherwise every seed is the
    # same instance and a system can be tuned on the one it is certified with.
    s1, s2 = rng.sample(["server", "database", "worker", "transport"], 2)
    k1, k2 = rng.sample(["host", "port", "address", "endpoint"], 2)
    k3 = rng.choice(["level", "format", "target"])
    v1 = rng.choice(["example.org", "10.0.0.4", "svc.internal"])
    v2 = str(rng.randint(1024, 9999))
    v3 = rng.choice(["debug", "info", "warning"])
    jk1, jk2 = rng.sample(["host", "port", "user", "region"], 2)
    jv1, jv2 = rng.choice(["localhost", "eu-west"]), str(rng.randint(1000, 9999))
    ext = rng.choice(["yaml", "toml", "xml", "cfg"])
    subst = dict(s1=s1, s2=s2, k1=k1, k2=k2, k3=k3, v1=v1, v2=v2, v3=v3,
                 jk1=jk1, jv1=jv1, jk2=jk2, jv2=jv2, ext=ext)

    pkg = work / "conf"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "loader.py").write_text(_LOADER, encoding="utf-8")
    fx = work / "fixtures"
    fx.mkdir()
    (fx / "old.json").write_text(json.dumps({jk1: jv1, jk2: int(jv2)}), encoding="utf-8")
    (fx / "new.ini").write_text(
        "# %s settings\n[%s]\n%s = %s\n%s = %s\n\n; and the rest\n[%s]\n%s = %s\n"
        % (s1, s1, k1, v1, k2, v2, s2, k3, v3), encoding="utf-8")
    (fx / "broken.ini").write_text(
        "[%s]\n%s = %s\nthis line has no equals sign\n" % (s1, k1, v1),
        encoding="utf-8")
    (fx / ("mystery.%s" % ext)).write_text("%s: %s\n" % (k1, v1), encoding="utf-8")
    (work / "tests").mkdir()
    (work / "tests" / "test_loader.py").write_text(
        "import os\nfrom conf.loader import load\n\n"
        "FIX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'fixtures')\n\n\n"
        "def test_json():\n"
        "    assert load(os.path.join(FIX, 'old.json'))['%s'] == '%s'\n" % (jk2, jv2),
        encoding="utf-8")
    (work / "README.md").write_text(
        "# conf\n\nLoads configuration. Supported formats are listed here and "
        "this list is the documentation of record.\n\n- JSON (`.json`)\n",
        encoding="utf-8")
    kfx = keyed / "fixtures"
    kfx.mkdir()
    for f in fx.iterdir():
        shutil.copy2(f, kfx / f.name)
    (keyed / "test_hidden_loader.py").write_text(_HIDDEN_TESTS % subst, encoding="utf-8")


def _v_config(work: Path, keyed: Path) -> Verdict:
    note = ("six withheld tests: backward compatibility on JSON, section "
            "flattening, string values, comment handling, the malformed file "
            "raising the module's own ConfigError, and unknown extensions still "
            "being refused. Documentation and the visible test file are checked "
            "for presence only -- their content is not judged")
    # The hidden suite reads fixtures beside itself, so stage them together.
    staged = work / "_hidden_fixtures_holder"
    if staged.exists():
        shutil.rmtree(staged)
    staged.mkdir()
    shutil.copytree(keyed / "fixtures", staged / "fixtures")
    test_src = (keyed / "test_hidden_loader.py").read_text(encoding="utf-8")
    (staged / "test_hidden_loader.py").write_text(test_src, encoding="utf-8")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
             str(staged / "test_hidden_loader.py")],
            cwd=str(work), capture_output=True, text=True, timeout=180)
        ok = r.returncode == 0
        tail = (r.stdout or "")[-1200:]
    except subprocess.TimeoutExpired:
        ok, tail = False, "hidden tests timed out"
    finally:
        shutil.rmtree(staged, ignore_errors=True)

    readme = (work / "README.md").read_text(encoding="utf-8") if (work / "README.md").exists() else ""
    documented = "ini" in readme.lower()
    reasons = []
    if not ok:
        reasons.append("hidden tests failed:\n%s" % tail[-600:])
    if not documented:
        reasons.append("README.md still lists only JSON; the task said it is the "
                       "documentation of record")
    return Verdict(ok and documented,
                   {"hidden_tests_passed": float(ok), "documented": float(documented)},
                   tuple(reasons), note, None)


config_format = Generator(
    key="t2.config_format", family="software", level="DL2",
    difficulty=Difficulty(horizon=3, coordination=2, uncertainty=2, tooling=1, verification=1),
    loss=Loss(value=1.0, c_detect=0.4, c_undo=0.4),
    prompt=("This package loads JSON configuration. Add support for INI files "
            "as well: sections become key prefixes, so `[server] host = x` "
            "loads as `server.host`. Comments beginning with # or ; are "
            "ignored. A file that cannot be understood must still raise the "
            "module's ConfigError rather than leaking a lower-level exception. "
            "JSON must keep working exactly as it does now. Update the visible "
            "tests and the README, which is the documentation of record."),
    deliverables=("conf/loader.py", "README.md"),
    verifier_note=("six withheld tests including backward compatibility and the "
                   "malformed-input path; README is checked for the format name "
                   "only, and its prose is not judged"),
    build=_b_config, verify=_v_config,
)


# -- DL2: a pipeline with a corrupt record --------------------------------

def _b_pipeline(work: Path, keyed: Path, rng: random.Random) -> None:
    regions = ["north", "south", "east", "west"]
    rows, truth = [], {r: 0.0 for r in regions}
    for _ in range(rng.randint(60, 90)):
        reg = rng.choice(regions)
        amt = round(rng.uniform(5, 500), 2)
        rows.append("%s,%s,%.2f" % (reg, "2026-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28)), amt))
        truth[reg] += amt
    # The planted failure: two records the reader must reject, not crash on.
    rows.insert(rng.randint(1, len(rows)), "north,2026-13-45,88.00")
    rows.insert(rng.randint(1, len(rows)), "south,2026-04-04,not-a-number")
    rng.shuffle(rows)
    (work / "sales.csv").write_text("region,date,amount\n" + "\n".join(rows) + "\n",
                                    encoding="utf-8")
    (work / "SPEC.md").write_text(
        "# Report\n\nProduce `report.json` with:\n\n"
        "- `totals`: an object mapping each region to the sum of its valid "
        "amounts, rounded to 2 decimal places\n"
        "- `rejected`: the number of rows that could not be used\n"
        "- `top_region`: the region with the largest total\n\n"
        "A row is unusable if its amount is not a number or its date is not a "
        "real calendar date. Unusable rows are counted and excluded, never "
        "guessed at, and must not stop the run.\n", encoding="utf-8")
    top = max(truth, key=lambda k: truth[k])
    (keyed / "expected.json").write_text(json.dumps(
        {"totals": {k: round(v, 2) for k, v in truth.items()},
         "rejected": 2, "top_region": top}, sort_keys=True), encoding="utf-8")


def _v_pipeline(work: Path, keyed: Path) -> Verdict:
    note = ("totals compared to 0.01, plus the rejected count and the top "
            "region; two rows are unusable and a run that crashes on them, or "
            "silently coerces them to zero, gets a different rejected count")
    if missing(work, "report.json"):
        return Verdict(False, {}, ("report.json was not produced",), note, 0.0)
    try:
        got = read_json(work / "report.json")
    except Exception as e:
        return Verdict(False, {}, ("report.json is not valid JSON: %s" % e,), note, 0.0)
    want = read_json(keyed / "expected.json")
    reasons, worst = [], 0.0
    for reg, v in want["totals"].items():
        g = float(got.get("totals", {}).get(reg, -1))
        worst = max(worst, abs(g - v))
        if abs(g - v) > 0.01:
            reasons.append("total for %s: expected %.2f, got %.2f" % (reg, v, g))
    if int(got.get("rejected", -1)) != want["rejected"]:
        reasons.append("rejected: expected %d, got %r" % (want["rejected"], got.get("rejected")))
    if got.get("top_region") != want["top_region"]:
        reasons.append("top_region: expected %s, got %r" % (want["top_region"], got.get("top_region")))
    return Verdict(not reasons, {"worst_total_error": worst}, tuple(reasons), note, 0.0)


pipeline = Generator(
    key="t2.pipeline", family="data", level="DL2",
    difficulty=Difficulty(horizon=3, coordination=2, uncertainty=2, tooling=1),
    loss=Loss(value=1.0, c_detect=0.5, c_undo=0.3),
    prompt="Read SPEC.md and produce what it asks for from sales.csv.",
    deliverables=("report.json",),
    verifier_note=("numeric totals to 0.01 plus the count of unusable rows; "
                   "two rows are planted invalid"),
    build=_b_pipeline, verify=_v_pipeline,
)


# -- DL3: an outcome, a constraint, and a cause the agent must find -------

_SLOW_SEARCH = '''\
"""In-memory search over a small document set."""


def _tokenise(text):
    return [t for t in text.lower().replace(",", " ").replace(".", " ").split() if t]


def build_index(documents):
    """Return the structure `search` reads."""
    return [(i, _tokenise(d)) for i, d in enumerate(documents)]


def search(index, query, limit=5):
    """Return up to `limit` document ids matching every term in `query`."""
    terms = _tokenise(query)
    hits = []
    for doc_id, tokens in index:
        # Membership against a list, once per term, per document.
        if all(any(tok == term for tok in tokens) for term in terms):
            hits.append(doc_id)
    # Deduplicate while preserving order.
    unique = []
    for h in hits:
        seen = False
        for u in unique:
            if u == h:
                seen = True
                break
        if not seen:
            unique.append(h)
    return unique[:limit]
'''


def _b_latency(work: Path, keyed: Path, rng: random.Random) -> None:
    vocab = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
             "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron", "pi"]
    docs = [" ".join(rng.choice(vocab) for _ in range(rng.randint(30, 60)))
            for _ in range(1200)]
    (work / "corpus.json").write_text(json.dumps(docs), encoding="utf-8")
    (work / "search.py").write_text(_SLOW_SEARCH, encoding="utf-8")
    (work / "GOAL.md").write_text(
        "# Goal\n\nQueries against this corpus are too slow.\n\n"
        "Make `search.py` answer the same queries **at least 25% faster**, "
        "measured over a query set you will not see, with **no change to the "
        "results**: for every query, the returned ids and their order must be "
        "identical to what the current code returns.\n\n"
        "You may change `search.py` however you like, including the shape "
        "returned by `build_index`, as long as the module still exposes "
        "`build_index(documents)` and `search(index, query, limit=5)`. You may "
        "not precompute answers for specific queries, and you may not change "
        "`corpus.json`.\n", encoding="utf-8")
    # Withheld queries: same vocabulary, never shown.
    queries = [" ".join(rng.choice(vocab) for _ in range(rng.randint(1, 3)))
               for _ in range(240)]
    (keyed / "queries.json").write_text(json.dumps(queries), encoding="utf-8")
    (keyed / "reference_search.py").write_text(_SLOW_SEARCH, encoding="utf-8")
    (keyed / "corpus.json").write_text(json.dumps(docs), encoding="utf-8")


_TIMER = '''\
import json, sys, time, importlib.util

mod_path, corpus_path, queries_path, out_path = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("cand", mod_path)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
docs = json.load(open(corpus_path)); queries = json.load(open(queries_path))

best = None
results = None
for _ in range(3):
    t0 = time.perf_counter()
    idx = m.build_index(docs)
    r = [m.search(idx, q) for q in queries]
    dt = time.perf_counter() - t0
    best = dt if best is None else min(best, dt)
    results = r
json.dump({"seconds": best, "results": results}, open(out_path, "w"))
'''


def _v_latency(work: Path, keyed: Path) -> Verdict:
    note = ("the candidate and the original are timed in the same session, "
            "best-of-three each, on 240 queries the agent never saw; results "
            "must match the reference exactly. Timing is wall-clock and "
            "therefore noisy -- the 25% bar is checked against the best of "
            "three runs of each, and a margin this small would need repetition "
            "to be a measurement rather than a reading")
    if missing(work, "search.py"):
        return Verdict(False, {}, ("search.py is gone",), note, None)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "timer.py").write_text(_TIMER, encoding="utf-8")
        outs = {}
        for name, mod in (("ref", keyed / "reference_search.py"), ("cand", work / "search.py")):
            o = td / ("%s.json" % name)
            r = subprocess.run(
                [sys.executable, str(td / "timer.py"), str(mod),
                 str(keyed / "corpus.json"), str(keyed / "queries.json"), str(o)],
                capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                return Verdict(False, {}, ("%s failed to run: %s" % (name, (r.stderr or "")[-400:]),),
                               note, None)
            outs[name] = json.loads(o.read_text())

    ref, cand = outs["ref"], outs["cand"]
    n = len(ref["results"])
    same = sum(1 for a, b in zip(ref["results"], cand["results"]) if a == b)
    fidelity = same / n if n else 0.0
    speedup = (ref["seconds"] - cand["seconds"]) / ref["seconds"] if ref["seconds"] else 0.0
    reasons = []
    if fidelity < 0.99:
        reasons.append("results differ on %d of %d queries" % (n - same, n))
    if speedup < 0.25:
        reasons.append("speedup %.1f%% is below the 25%% required" % (100 * speedup))
    return Verdict(not reasons,
                   {"speedup_fraction": speedup, "result_fidelity": fidelity,
                    "reference_seconds": ref["seconds"], "candidate_seconds": cand["seconds"]},
                   tuple(reasons), note, None)


search_latency = Generator(
    key="t3.search_latency", family="software", level="DL3",
    difficulty=Difficulty(horizon=3, coordination=2, uncertainty=3, ambiguity=2,
                          tooling=2, verification=2, novelty=1),
    loss=Loss(value=1.0, c_detect=0.6, c_undo=0.4),
    prompt="Read GOAL.md.",
    deliverables=("search.py",),
    verifier_note=("timed against the original in the same session on withheld "
                   "queries, with exact result equality required; wall-clock "
                   "timing is noisy and the margin is not large"),
    build=_b_latency, verify=_v_latency,
)

ALL = (config_format, pipeline, search_latency)

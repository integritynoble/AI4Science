"""A capable-but-careless solver, and the checks it can derive without help.

This exists to make the harness's claim testable rather than plausible. The
solver is deliberately ordinary: it can perform every operation the tasks need,
and on its first pass it makes the mistake a real attempt makes -- first-wins
deduplication, a date read in the wrong order, a global search and replace, bad
rows coerced to zero, numbers emitted as strings. None of these is stupidity.
Each is the reading the statement permits if you do not check.

The point is that the *same solver* is run twice: bare, and inside the harness.
Nothing about its ability changes between the two runs. If the frontier moves,
it moved because the class became checkable, which is the claim.

**The criteria are derived from visible material only.** The task statement, the
rules file, the input data, and a snapshot of the workspace before the work.
Never the benchmark's hidden verifier -- that stays the acceptor of record, and
an agent that could read it would be grading its own work with the answer in
hand.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .contract import Contract

# The derived checks are small Python programs. They are carried as source and
# written to a file by the acceptor rather than squeezed through a shell: the
# first version used `python3 -c "..."` and json-escaped newlines arrived as
# literal backslash-n, so every check died of a syntax error while the harness
# appeared to work. Carrying source removes the whole class of bug.
def _q(code: str) -> str:
    return "pycode:" + code


class CarelessSolver:
    """Does the work. Does not check it. Corrects when told what failed."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.pass_no = 0

    # -- what it can work out about "done", from what it was given ---------

    def propose_criteria(self, contract: Contract, ws: Path
                         ) -> Sequence[Tuple[str, str, str]]:
        fn = getattr(self, "_crit_" + self.key.replace(".", "_"), None)
        return fn(ws) if fn else []

    def _crit_t0_csv_to_json(self, ws: Path) -> Sequence[Tuple[str, str, str]]:
        # The statement names the keys and their types. That is a check.
        return [(
            "shape_and_types",
            _q("import json,csv\n"
               "rows=json.load(open('out.json'))\n"
               "src=list(csv.DictReader(open('data.csv')))\n"
               "assert isinstance(rows,list) and len(rows)==len(src), 'row count'\n"
               "for a,b in zip(rows,src):\n"
               " assert set(a)=={'city','count','score'}, 'keys'\n"
               " assert isinstance(a['city'],str), 'city must be a string'\n"
               " assert isinstance(a['count'],int), 'count must be an integer'\n"
               " assert isinstance(a['score'],(int,float)), 'score must be a number'\n"
               " assert a['city']==b['city'] and str(a['count'])==b['count'].strip()\n"),
            "row count, key set, declared types, and city/count agreement with "
            "the source. Does not check the score's precision"),
        ]

    def _crit_t0_extract_fields(self, ws: Path) -> Sequence[Tuple[str, str, str]]:
        # Anything extracted must appear verbatim in the document it came from.
        # Derivable with no knowledge of the answer, and it catches a number
        # that lost its cents.
        return [(
            "values_appear_verbatim_in_source",
            _q("import json\n"
               "d=json.load(open('fields.json'))\n"
               "t=open('report.txt').read()\n"
               "for k in ('reference','amount','due'):\n"
               " assert k in d, 'missing field '+k\n"
               " s=('%.2f'%d[k]) if k=='amount' else str(d[k])\n"
               " assert s in t, k+' value '+s+' does not appear in report.txt'\n"),
            "each extracted value appears verbatim in the source. Does not "
            "check that the RIGHT occurrence was taken when a value repeats"),
        ]

    def _crit_t1_clean_dataset(self, ws: Path) -> Sequence[Tuple[str, str, str]]:
        # RULES.md states the rules. Each becomes a check, including the one
        # about which duplicate wins -- which is the whole trap.
        return [
            ("iso_dates_and_no_empty_names",
             _q("import csv\n"
                "import re\n"
                "rows=list(csv.DictReader(open('cleaned.csv')))\n"
                "assert rows, 'no rows'\n"
                "for r in rows:\n"
                " assert r['name'].strip(), 'an empty name survived'\n"
                " assert re.fullmatch(r'\\d{4}-\\d{2}-\\d{2}', r['date']), 'not ISO: '+r['date']\n"),
             "rule 1 and rule 3 from RULES.md. Does not check which duplicate won"),
            ("last_occurrence_wins",
             _q("import csv\n"
                "raw=list(csv.DictReader(open('raw.csv')))\n"
                "out={r['id']:r for r in csv.DictReader(open('cleaned.csv'))}\n"
                "last={}\n"
                "for r in raw:\n"
                " if r['name'].strip(): last[r['id']]=r\n"
                "assert len(out)==len(last), 'kept %d ids, expected %d'%(len(out),len(last))\n"
                "for i,r in last.items():\n"
                " assert i in out, 'lost id '+i\n"
                " assert out[i]['name']==r['name'], 'id '+i+' kept the wrong row'\n"
                " d,m,y=r['date'].split('/')\n"
                " assert out[i]['date']=='%s-%s-%s'%(y,m,d), 'id '+i+' date '+out[i]['date']\n"),
             "rule 2: the LAST occurrence of a repeated id is the correction, "
             "and the source dates are DD/MM. Compares every kept row against "
             "the raw file"),
        ]

    def _crit_t1_request_timeout(self, ws: Path) -> Sequence[Tuple[str, str, str]]:
        # The goal names one thing to change and two to leave alone. The second
        # half is checkable against the snapshot taken before the work.
        goal = (ws / "GOAL.md").read_text(encoding="utf-8") if (ws / "GOAL.md").exists() else ""
        want = re.search(r"wait (\d+) seconds", goal)
        now = re.search(r"current (\d+)", goal)
        want_v = want.group(1) if want else "30"
        now_v = now.group(1) if now else "5"
        return [
            ("the_named_value_changed",
             _q("import glob,re,sys\n"
                "hits=[p for p in glob.glob('*/http.py') if re.search(r'REQUEST_TIMEOUT\\s*=\\s*%s', open(p).read())]\n"
                "assert hits, 'REQUEST_TIMEOUT is not %s anywhere'\n" % (want_v, want_v)),
             "the request timeout now holds the value the goal named"),
            ("the_neighbours_did_not_move",
             _q("import glob,re\n"
                "for p in glob.glob('*/cache.py')+glob.glob('*/retry.py'):\n"
                " t=open(p).read()\n"
                " assert re.search(r'=\\s*%s\\b', t), p+' changed; the goal said to leave it'\n" % now_v),
             "the cache and retry constants still hold their original value. "
             "This is the check a global search and replace fails"),
        ]

    def _crit_t2_pipeline(self, ws: Path) -> Sequence[Tuple[str, str, str]]:
        # SPEC.md says unusable rows are counted and excluded, never guessed at.
        # The agent can count them itself from the input.
        return [
            ("rejected_count_matches_the_input",
             _q("import csv,json,datetime\n"
                "bad=0\n"
                "for r in csv.DictReader(open('sales.csv')):\n"
                " try:\n"
                "  float(r['amount']); datetime.date.fromisoformat(r['date'])\n"
                " except Exception: bad+=1\n"
                "rep=json.load(open('report.json'))\n"
                "assert rep.get('rejected')==bad, 'rejected %r, the input has %d unusable rows'%(rep.get('rejected'),bad)\n"),
             "the number of unusable rows the report claims equals the number "
             "the input actually contains. This is the check that coercing bad "
             "rows to zero fails"),
            ("totals_exclude_the_unusable_rows",
             _q("import csv,json,datetime\n"
                "tot={}\n"
                "for r in csv.DictReader(open('sales.csv')):\n"
                " try:\n"
                "  a=float(r['amount']); datetime.date.fromisoformat(r['date'])\n"
                " except Exception: continue\n"
                " tot[r['region']]=tot.get(r['region'],0.0)+a\n"
                "rep=json.load(open('report.json'))['totals']\n"
                "for k,v in tot.items():\n"
                " assert abs(rep.get(k,-1)-round(v,2))<=0.01, 'total for '+k\n"),
             "each regional total equals the sum of the usable rows only"),
        ]

    # -- doing the work ----------------------------------------------------

    def attempt(self, contract: Contract, ws: Path, feedback: Sequence[str]) -> float:
        self.pass_no += 1
        careful = self.pass_no > 1
        fn = getattr(self, "_do_" + self.key.replace(".", "_"), None)
        if fn is None:
            return 0.0
        fn(ws, careful)
        # Calibrated the way an ordinary agent is: confident on a first pass,
        # and it has no idea it was wrong. This is why the check has to exist
        # outside it.
        return 0.92 if not careful else 0.97

    def _do_t0_csv_to_json(self, ws: Path, careful: bool) -> None:
        rows = list(csv.DictReader((ws / "data.csv").open(encoding="utf-8", newline="")))
        if careful:
            out = [{"city": r["city"], "count": int(r["count"]), "score": float(r["score"])}
                   for r in rows]
        else:                       # everything as it came off the file: strings
            out = [{"city": r["city"], "count": r["count"], "score": r["score"]}
                   for r in rows]
        (ws / "out.json").write_text(json.dumps(out, indent=2, sort_keys=True),
                                     encoding="utf-8")

    def _do_t0_extract_fields(self, ws: Path, careful: bool) -> None:
        t = (ws / "report.txt").read_text(encoding="utf-8")
        ref = re.search(r"reference for this note is\s+(REF-\d+)", t).group(1)
        raw = re.search(r"Settlement of ([\d.]+)", t).group(1)
        amount = float(raw) if careful else int(float(raw))
        due = re.search(r"(\d{4}-\d{2}-\d{2})", t).group(1)
        (ws / "fields.json").write_text(json.dumps(
            {"reference": ref, "amount": amount, "due": due}, sort_keys=True),
            encoding="utf-8")

    def _do_t1_clean_dataset(self, ws: Path, careful: bool) -> None:
        rows = list(csv.DictReader((ws / "raw.csv").open(encoding="utf-8", newline="")))
        out: List[Dict[str, str]] = []
        if careful:
            last = {r["id"]: i for i, r in enumerate(rows) if r["name"].strip()}
            for i, r in enumerate(rows):
                if r["name"].strip() and last[r["id"]] == i:
                    d, m, y = r["date"].split("/")
                    out.append({"id": r["id"], "name": r["name"],
                                "date": "%s-%s-%s" % (y, m, d)})
        else:                       # first wins, and the date read as US order
            seen = set()
            for r in rows:
                if not r["name"].strip() or r["id"] in seen:
                    continue
                seen.add(r["id"])
                m, d, y = r["date"].split("/")
                out.append({"id": r["id"], "name": r["name"],
                            "date": "%s-%s-%s" % (y, m, d)})
        with (ws / "cleaned.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["id", "name", "date"])
            w.writeheader()
            w.writerows(out)

    def _do_t1_request_timeout(self, ws: Path, careful: bool) -> None:
        goal = (ws / "GOAL.md").read_text(encoding="utf-8")
        want = int(re.search(r"wait (\d+) seconds", goal).group(1))
        now = int(re.search(r"current (\d+)", goal).group(1))
        pkg = next(d for d in ws.iterdir() if d.is_dir() and (d / "http.py").exists())
        if careful:
            p = pkg / "http.py"
            p.write_text(re.sub(r"^REQUEST_TIMEOUT = \d+", "REQUEST_TIMEOUT = %d" % want,
                                p.read_text(encoding="utf-8"), flags=re.M), encoding="utf-8")
        else:                       # replace the number wherever it appears
            for name in ("http.py", "cache.py", "retry.py"):
                p = pkg / name
                p.write_text(p.read_text(encoding="utf-8").replace("= %d" % now, "= %d" % want),
                             encoding="utf-8")

    def _do_t2_pipeline(self, ws: Path, careful: bool) -> None:
        import datetime
        totals: Dict[str, float] = {}
        rejected = 0
        for r in csv.DictReader((ws / "sales.csv").open(encoding="utf-8", newline="")):
            try:
                amt = float(r["amount"])
                datetime.date.fromisoformat(r["date"])
            except (ValueError, TypeError):
                if careful:
                    rejected += 1
                    continue
                amt = 0.0           # coerced, and the count never happens
            totals[r["region"]] = totals.get(r["region"], 0.0) + amt
        (ws / "report.json").write_text(json.dumps(
            {"totals": {k: round(v, 2) for k, v in totals.items()},
             "rejected": rejected,
             "top_region": max(totals, key=lambda k: totals[k])}, sort_keys=True),
            encoding="utf-8")


#: The tasks this solver covers. Chosen because each has a known careless
#: reading, so the bare run fails for a reason rather than at random.
COVERED = ("t0.csv_to_json", "t0.extract_fields", "t1.clean_dataset",
           "t1.request_timeout", "t2.pipeline")


class StubbornSolver(CarelessSolver):
    """Capable of acting, incapable of getting it right, and sure of itself.

    Feedback changes nothing: every pass takes the careless reading. This is the
    case that separates a delegation harness from a retry loop. A retry loop
    runs it three times and hands back the third wrong answer. A harness never
    accepts it, and says so.

    It is also the honest control for the experiment. Without it the harness's
    result would only show that retrying a solver whose second attempt is
    correct produces a correct result, which is not a claim about delegation.
    """

    def attempt(self, contract, ws: Path, feedback: Sequence[str]) -> float:
        self.pass_no += 1
        fn = getattr(self, "_do_" + self.key.replace(".", "_"), None)
        if fn is None:
            return 0.0
        fn(ws, False)              # careless, every time, whatever it is told
        return 0.93                # and confident, which is the whole problem

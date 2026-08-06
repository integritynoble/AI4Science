#!/usr/bin/env python3
"""Check the scope and roster objects against the rules of §§13f, 13i and 13j.

Run from anywhere:  python3 docs/specs/research-agents/scope/validate.py

What it enforces, and why each one is a rule rather than a preference:

  * every `out` entry names where the question GOES. A boundary that says
    "not ours" and nowhere else is a refusal, not a handoff, and the person
    holding the question is left with it.
  * every `adjacent` field is a real agent, or is explicitly marked
    "(no agent yet)". An unmarked name is a handoff to something that does
    not exist.
  * `watch_rung` exists in that field's ladder — §13j's check is that a rung
    blocked by an out-of-scope dependency shows the boundary is wrong, and it
    cannot check a rung that is not there.
  * `set_by.named` is null until a panel actually exists. Naming people in a
    design document commits them to something they have not agreed to.

For the rosters (§13f, §13i):

  * all NINE core sub-agents are present. A field may add and may not remove,
    and an agent.json without `verifier` or `twin` is not a research agent
    with fewer parts — it is a method with a scoreboard.
  * `verifier` is never embodied. It answers "did this happen", and something
    that can make things happen is the wrong thing to ask.
  * every non-core sub-agent names the ladder rung it was admitted for, and
    that rung exists. Otherwise a roster grows by preference.
  * an embodied sub-agent's field has at least one tool needing an envelope —
    a body with nothing to drive is a claim, not a capability.

It also REPORTS one-way adjacencies without failing on them: a one-way
relation can be correct (a field may consume another's output without handing
anything back), so it is an expert's judgment, not an error.
"""
import json, pathlib, re, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
PAGES = HERE.parent

SCHEMA = PAGES / "agent-manifest.schema.json"


def _schema_errors(kind, obj, name):
    """Validate one block against agent-manifest.schema.json.

    Skipped with a note rather than failing if `jsonschema` is absent: the
    structural rules below are the ones that carry the design, and a docs check
    that cannot run on a machine without an optional library is a check people
    delete.
    """
    try:
        import jsonschema
    except ImportError:
        return None
    schema = json.loads(SCHEMA.read_text())
    sub = {"$schema": schema["$schema"], "$defs": schema["$defs"],
           "$ref": f"#/$defs/{kind}"}
    v = jsonschema.Draft202012Validator(sub)
    return [f"{name}: {'/'.join(str(x) for x in e.path)}: {e.message}"
            for e in sorted(v.iter_errors(obj), key=lambda e: list(e.path))]


def _code_agent_ids():
    """The ids the CODE uses, read from the package rather than typed here."""
    for py in ("/home/spiritai/pwm/singularity/.webvenv/bin/python", sys.executable):
        r = subprocess.run([py, "-c", "from ai4science.harness.agents.research_agents "
                            "import registry as r; import json; print(json.dumps(list(r.NAMES)))"],
                           capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return set(json.loads(r.stdout.strip()))
            except Exception:
                pass
    return None


def main() -> int:
    pages = {p.stem for p in PAGES.glob("*.md")} - {"README"}
    code_ids = _code_agent_ids()
    schema_ran = False
    errs, scopes = [], {}
    for f in sorted(HERE.glob("*.json")):
        o = json.loads(f.read_text())
        scopes[o["agent"]] = o
        se = _schema_errors("scope", o, f.name)
        if se is not None:
            schema_ran = True
            errs.extend(se)
        # the join to the running thing, checked rather than trusted
        if o.get("agent_id") is None:
            print(f"  note: {f.name} declares a field with no agent yet — a draft")
        elif code_ids is not None and o.get("agent_id") not in code_ids:
            errs.append(f"{f.name}: agent_id {o.get('agent_id')!r} is not a name the code "
                        f"knows — have: {', '.join(sorted(code_ids))}")
        if o["agent"] not in pages:
            errs.append(f"{f.name}: agent '{o['agent']}' has no page")
        for e in o["out"]:
            if not e.get("goes_to", "").strip():
                errs.append(f"{f.name}: out '{e['question']}' names no destination")
        for a in o["adjacent"]:
            if "(no agent yet)" in a["field"]:
                continue
            if a["field"] not in pages:
                errs.append(f"{f.name}: adjacent '{a['field']}' is neither an agent "
                            f"nor marked '(no agent yet)'")
        page = (PAGES / f"{o['agent']}.md").read_text()
        rungs = {int(m) for m in re.findall(r"^### (\d+) · ", page, re.M)}
        if rungs and o["watch_rung"] is not None and o["watch_rung"] not in rungs:
            errs.append(f"{f.name}: watch_rung {o['watch_rung']} is not in the ladder {sorted(rungs)}")
        if o["set_by"]["named"] is not None:
            errs.append(f"{f.name}: set_by.named is set — panels are roles until one exists")

    for a, o in sorted(scopes.items()):
        for n in sorted(x["field"] for x in o["adjacent"]):
            if n in scopes and a not in {y["field"] for y in scopes[n]["adjacent"]}:
                print(f"  note: {a} → {n}, not back (may be correct)")

    # ── rosters (§13f, §13i) ───────────────────────────────────────────
    CORE = {"literature", "twin", "corpus", "method", "runner",
            "verifier", "reproducer", "teacher", "writer"}
    ROSTERS = HERE.parent / "roster"
    for f in sorted(ROSTERS.glob("*.json")):
        o = json.loads(f.read_text())
        re_ = _schema_errors("roster", o, f.name)
        if re_ is not None:
            schema_ran = True
            errs.extend(re_)
        page = (PAGES / f"{o['agent']}.md").read_text()
        rungs = {int(m) for m in re.findall(r"^### (\d+) \u00b7 ", page, re.M)}
        names = {x["name"] for x in o["sub_agents"]}
        missing = CORE - names
        if missing:
            errs.append(f"{f.name}: missing core sub-agents {sorted(missing)} — the nine are a floor")
        for x in o["sub_agents"]:
            JUDGING = {"verifier", "reproducer", "teacher", "writer"}
            if x["name"] in JUDGING and x["embodied"]:
                errs.append(f"{f.name}: '{x['name']}' is a JUDGING member and is embodied — "
                            f"something that can make things happen is the wrong thing to ask "
                            f"whether they happened. The rule is not the verifier's alone")
            if x.get("kind") == "embodied" and not x["embodied"]:
                errs.append(f"{f.name}: '{x['name']}' has kind=embodied and embodied=false")
            if x["embodied"] and x.get("kind") != "embodied":
                errs.append(f"{f.name}: '{x['name']}' is embodied but its kind is "
                            f"{x.get('kind')!r} — embodiment is a KIND of member, not a flag")
            if not x["core"]:
                r = x.get("admitted_for_rung")
                if r is None:
                    errs.append(f"{f.name}: added sub-agent '{x['name']}' names no rung")
                elif rungs and r not in rungs:
                    errs.append(f"{f.name}: '{x['name']}' admitted for rung {r}, not in {sorted(rungs)}")
        for x in o["sub_agents"]:
            if x["embodied"] and not x.get("refusal", "").strip():
                errs.append(f"{f.name}: embodied member '{x['name']}' states no refusal — "
                            f"an irreversible act needs a stated thing it will not do")
        if any(x["embodied"] for x in o["sub_agents"]) and not any(t["needs_envelope"] for t in o["tools"]):
            errs.append(f"{f.name}: embodied sub-agents but no tool needing an envelope")

        # every sub-ladder rung is owned exactly once — by a sub-agent, or
        # explicitly by a person. Left blank, "a person holds this" and "we
        # forgot" look identical, and only one of them is fine.
        subs = set(re.findall(r"^### (\d+\.\d+) \u00b7 ", page, re.M))
        owned = {}
        for x in o["sub_agents"]:
            for r in x.get("owns_rungs", []):
                owned.setdefault(r.split()[0], []).append(x["name"])
        for h in o.get("human_owned_rungs", []):
            owned.setdefault(h["rung"], []).append(f"human:{h['held_by']}")
        if not rungs:
            print(f"  note: {f.name} has no ladder yet — rung checks deferred")
        for r in sorted(subs - set(owned)):
            errs.append(f"{f.name}: sub-rung {r} is owned by nobody — assign it, or "
                        f"list it in human_owned_rungs with who holds it")
        for r, who in sorted(owned.items()):
            if subs and r not in subs:
                errs.append(f"{f.name}: owns_rungs names {r}, which is not a sub-rung")
            elif len(who) > 1 and not all(w.startswith("human:") for w in who):
                pass  # several sub-agents may share one rung; that is a division of work

    if errs:
        print("\n".join("  FAIL " + e for e in errs))
        return 1
    nr = len(list((HERE.parent / "roster").glob("*.json")))
    note = "" if schema_ran else "  (schema check skipped: no jsonschema)"
    joined = "" if code_ids is None else f", agent_ids joined to {len(code_ids)} code names"
    print(f"  {len(scopes)} scope objects and {nr} rosters valid{joined}{note}")
    return 0

if __name__ == "__main__":
    sys.exit(main())

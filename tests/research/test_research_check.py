import hashlib
from pathlib import Path
from ai4science.harness.agents.research.research_check import check_research, sha256_file

def _ws(tmp_path, report, sources, coverage, tamper=None):
    (tmp_path / "sources").mkdir(exist_ok=True)
    src_cfg = {}
    for name, content in sources.items():
        p = tmp_path / "sources" / name
        p.write_text(content)
        src_cfg[f"sources/{name}"] = hashlib.sha256(content.encode()).hexdigest()
    if tamper:                      # overwrite a source AFTER hashing (simulate agent edit)
        for name, content in tamper.items():
            (tmp_path / "sources" / name).write_text(content)
    (tmp_path / "report.md").write_text(report)
    config = {"report": "report.md", "sources": src_cfg, "coverage_points": coverage}
    return tmp_path, config

SRC = {"a.txt": "The sky is blue because of Rayleigh scattering of sunlight.\n",
       "b.txt": "Water boils at 100 degrees Celsius at sea level.\n"}

GOOD = (
    "# Report\n\n"
    "The sky appears blue due to scattering [S1]. This is a well-known effect "
    "that has been studied extensively across the physics literature for years [S1].\n\n"
    "Separately, water boils at a fixed temperature at sea level [S2], which is a "
    "standard reference point used throughout thermodynamics and everyday cooking [S2].\n\n"
    "## References\n"
    'S1: sources/a.txt — "Rayleigh scattering of sunlight"\n'
    'S2: sources/b.txt — "Water boils at 100 degrees Celsius"\n')

def test_grounded_report_passes(tmp_path):
    ws, cfg = _ws(tmp_path, GOOD, SRC, ["Rayleigh scattering", "water boils"])
    assert check_research(ws, cfg)["ok"] is True

def test_fabricated_quote_fails(tmp_path):
    bad = GOOD.replace('"Rayleigh scattering of sunlight"', '"quantum flux capacitor resonance"')
    ws, cfg = _ws(tmp_path, bad, SRC, ["Rayleigh scattering", "water boils"])
    r = check_research(ws, cfg)
    assert r["ok"] is False and "ground" in r["reason"].lower()

def test_source_tamper_fails(tmp_path):
    # agent edits sources/a.txt so a fabricated quote would "appear" -> SHA mismatch -> fail
    bad = GOOD.replace('"Rayleigh scattering of sunlight"', '"invented magic quote"')
    ws, cfg = _ws(tmp_path, bad, SRC, ["Rayleigh scattering", "water boils"],
                  tamper={"a.txt": "invented magic quote is now in the source\n"})
    r = check_research(ws, cfg)
    assert r["ok"] is False and ("integrity" in r["reason"].lower() or "tamper" in r["reason"].lower())

def test_claim_without_citation_fails(tmp_path):
    bad = GOOD.replace(" [S1]. This is a well-known effect "
                       "that has been studied extensively across the physics literature for years [S1].",
                       ". This is a well-known effect that has been studied extensively "
                       "across the physics literature for many years and decades.")
    ws, cfg = _ws(tmp_path, bad, SRC, ["Rayleigh scattering", "water boils"])
    r = check_research(ws, cfg)
    assert r["ok"] is False and "citation" in r["reason"].lower()

def test_dangling_marker_fails(tmp_path):
    bad = GOOD.replace("[S2]", "[S9]")
    ws, cfg = _ws(tmp_path, bad, SRC, ["Rayleigh scattering", "water boils"])
    assert check_research(ws, cfg)["ok"] is False

def test_missing_coverage_point_fails(tmp_path):
    ws, cfg = _ws(tmp_path, GOOD, SRC, ["Rayleigh scattering", "water boils", "photosynthesis pathways"])
    r = check_research(ws, cfg)
    assert r["ok"] is False and "coverage" in r["reason"].lower()

def test_missing_references_section_fails(tmp_path):
    bad = GOOD.split("## References")[0]
    ws, cfg = _ws(tmp_path, bad, SRC, ["Rayleigh scattering", "water boils"])
    assert check_research(ws, cfg)["ok"] is False

def test_whitespace_normalized_match(tmp_path):
    src = {"a.txt": "The   sky is\nblue because of Rayleigh   scattering of sunlight.\n"}
    good = GOOD.replace('S2: sources/b.txt — "Water boils at 100 degrees Celsius"\n', "")
    good = good.replace(" [S2]", " [S1]")   # avoid dangling; both cite S1
    ws, cfg = _ws(tmp_path, good, src, ["Rayleigh scattering"])
    assert check_research(ws, cfg)["ok"] is True

def test_missing_report_fails(tmp_path):
    cfg = {"report": "report.md", "sources": {}, "coverage_points": []}
    assert check_research(tmp_path, cfg)["ok"] is False

def test_sha256_file_helper(tmp_path):
    p = tmp_path / "x.txt"; p.write_text("hello\n")
    import hashlib
    assert sha256_file(p) == hashlib.sha256(b"hello\n").hexdigest()

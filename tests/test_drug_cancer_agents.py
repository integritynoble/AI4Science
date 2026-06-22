"""Tests for drug-design and cancer specific agents."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(tmp_path):
    from ai4science.harness.agents.context import BuildContext
    return BuildContext(workspace=tmp_path, brand_provider=None, session_factory=None)


# ---------------------------------------------------------------------------
# Registry: both agents are discovered and correctly configured
# ---------------------------------------------------------------------------

def test_drug_design_agent_in_registry():
    from ai4science.harness.agents import registry
    registry.reload()
    spec = registry.get("drug-design")
    assert spec is not None
    assert spec.category == "specific"
    assert spec.tier == "science"
    assert "drug-design" in spec.capabilities


def test_cancer_agent_in_registry():
    from ai4science.harness.agents import registry
    registry.reload()
    spec = registry.get("cancer")
    assert spec is not None
    assert spec.category == "specific"
    assert spec.tier == "science"
    assert "cancer" in spec.capabilities


def test_drug_design_aliases():
    from ai4science.harness.agents import registry
    registry.reload()
    for alias in ("drug", "docking", "medicinal chemistry"):
        assert registry.get(alias) is not None, f"alias '{alias}' not found"
        assert registry.get(alias).name == "drug-design"


def test_cancer_aliases():
    from ai4science.harness.agents import registry
    registry.reload()
    for alias in ("oncology", "tumor"):
        assert registry.get(alias) is not None, f"alias '{alias}' not found"
        assert registry.get(alias).name == "cancer"


# ---------------------------------------------------------------------------
# Capabilities: bundles registered and tools loadable
# ---------------------------------------------------------------------------

def test_drug_design_capability_registered():
    from ai4science.harness.agents.capabilities import BUILTIN_BUNDLES
    assert "drug-design" in BUILTIN_BUNDLES


def test_cancer_capability_registered():
    from ai4science.harness.agents.capabilities import BUILTIN_BUNDLES
    assert "cancer" in BUILTIN_BUNDLES


def test_drug_design_tools_load(tmp_path):
    from ai4science.harness.agents.capabilities import resolve_capability
    tools = resolve_capability("drug-design", _ctx(tmp_path))
    names = {t.name for t in tools}
    for expected in ("drug_info", "drug_admet", "drug_similarity",
                     "drug_docking_prep", "drug_registry"):
        assert expected in names, f"drug-design tool '{expected}' missing"


def test_cancer_tools_load(tmp_path):
    from ai4science.harness.agents.capabilities import resolve_capability
    tools = resolve_capability("cancer", _ctx(tmp_path))
    names = {t.name for t in tools}
    for expected in ("cancer_gene_info", "cancer_variant", "cancer_pathways",
                     "cancer_trials", "cancer_registry"):
        assert expected in names, f"cancer tool '{expected}' missing"


# ---------------------------------------------------------------------------
# Drug-design tool behaviour (no network, no rdkit required)
# ---------------------------------------------------------------------------

def test_drug_docking_prep_no_files(tmp_path):
    from ai4science.harness.drug_design_tools import drug_design_tools
    tool = {t.name: t for t in drug_design_tools()}["drug_docking_prep"]
    out = tool.func(tmp_path, smiles="CCO", center_x=10.0, center_y=5.0, center_z=2.0)
    assert "Next Steps" in out
    assert "10.0" in out  # center_x reflected


def test_drug_docking_prep_warns_on_origin(tmp_path):
    from ai4science.harness.drug_design_tools import drug_design_tools
    tool = {t.name: t for t in drug_design_tools()}["drug_docking_prep"]
    out = tool.func(tmp_path)
    assert "WARNING" in out.upper() or "origin" in out.lower()


def test_drug_admet_no_rdkit_returns_helpful_message(tmp_path):
    """When rdkit is absent, drug_admet returns an install hint (not a crash)."""
    from ai4science.harness.drug_design_tools import drug_design_tools
    tool = {t.name: t for t in drug_design_tools()}["drug_admet"]
    # Remove rdkit from sys.modules to force the ImportError path
    rdkit_mods = {k for k in sys.modules if k.startswith("rdkit")}
    saved = {k: sys.modules.pop(k) for k in rdkit_mods}
    try:
        import builtins, importlib
        real_import = builtins.__import__
        def _fake_import(name, *a, **kw):
            if name.startswith("rdkit"):
                raise ImportError("no module named rdkit (mocked)")
            return real_import(name, *a, **kw)
        builtins.__import__ = _fake_import
        out = tool.func(tmp_path, smiles="CCO")
        assert "rdkit" in out.lower()
        assert "install" in out.lower() or "pip" in out.lower()
    finally:
        builtins.__import__ = real_import
        sys.modules.update(saved)


def test_drug_info_missing_args(tmp_path):
    from ai4science.harness.drug_design_tools import drug_design_tools
    tool = {t.name: t for t in drug_design_tools()}["drug_info"]
    out = tool.func(tmp_path)
    assert "provide" in out.lower() or "required" in out.lower()


# ---------------------------------------------------------------------------
# Cancer tool behaviour (no network)
# ---------------------------------------------------------------------------

def test_cancer_variant_kras_hotspot(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_variant"]
    out = tool.func(tmp_path, gene="KRAS", mutation="G12D")
    assert "ONCOGENIC HOTSPOT" in out


def test_cancer_variant_braf_v600e(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_variant"]
    out = tool.func(tmp_path, gene="BRAF", mutation="V600E")
    assert "ONCOGENIC HOTSPOT" in out
    assert "vemurafenib" in out.lower() or "dabrafenib" in out.lower()


def test_cancer_variant_vus(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_variant"]
    out = tool.func(tmp_path, gene="UNKNOWN_GENE", mutation="X99Z")
    assert "VUS" in out or "uncertain" in out.lower()


def test_cancer_variant_missing_args(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_variant"]
    out = tool.func(tmp_path, gene="", mutation="")
    assert "required" in out.lower()


def test_cancer_pathways_all(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_pathways"]
    out = tool.func(tmp_path)
    for pathway in ("RAS/MAPK", "PI3K", "p53", "WNT", "Notch", "Hedgehog", "checkpoint"):
        assert pathway in out, f"pathway '{pathway}' missing from output"


def test_cancer_pathways_filter_by_gene(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_pathways"]
    out = tool.func(tmp_path, gene="BRAF")
    assert "RAS/MAPK" in out
    # PI3K should not appear (BRAF is not in that pathway)
    assert "PI3K" not in out


def test_cancer_pathways_filter_by_pathway(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_pathways"]
    out = tool.func(tmp_path, pathway="Notch")
    assert "NOTCH1" in out
    assert "T-ALL" in out


def test_cancer_gene_missing_symbol(tmp_path):
    from ai4science.harness.cancer_tools import cancer_tools
    tool = {t.name: t for t in cancer_tools()}["cancer_gene_info"]
    out = tool.func(tmp_path, gene="")
    assert "required" in out.lower()


# ---------------------------------------------------------------------------
# Moat: both new agents are science-tier (not open)
# ---------------------------------------------------------------------------

def test_new_agents_are_science_tier():
    from ai4science.harness.agents import registry
    registry.reload()
    for name in ("drug-design", "cancer"):
        spec = registry.get(name)
        assert spec.tier == "science", f"{name} should be science tier (PWM moat)"

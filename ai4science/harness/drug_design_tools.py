"""Drug-design domain tools for the drug-design specific agent.

Provides:
  drug_info           — look up a molecule by name/SMILES/InChI (PubChem)
  drug_admet          — predict ADMET properties from SMILES (rule-based + heuristic)
  drug_docking_prep   — validate & prep a docking run (receptor + ligand paths)
  drug_similarity     — Tanimoto fingerprint similarity between two SMILES strings
  drug_registry       — search PWM registry for drug-design problems and solutions
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ai4science.harness.tools.base import Tool

_STR = {"type": "string"}
_OPT_STR = {"type": "string", "default": ""}


# ---------------------------------------------------------------------------
# 1. Molecule info lookup (PubChem REST, public, no key required)
# ---------------------------------------------------------------------------

def _drug_info_tool() -> Tool:
    def _info(workspace, *, name: str = "", smiles: str = "", cid: str = "") -> str:
        import urllib.request, urllib.error
        if cid:
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/JSON"
            query_label = f"CID={cid}"
        elif smiles:
            import urllib.parse
            enc = urllib.parse.quote(smiles, safe="")
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{enc}/JSON"
            query_label = f"SMILES={smiles[:40]}"
        elif name:
            import urllib.parse
            enc = urllib.parse.quote(name, safe="")
            url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{enc}/JSON"
            query_label = f"name={name}"
        else:
            return "[drug_info] provide name, smiles, or cid"
        try:
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return f"[drug_info] not found ({e.code}): {query_label}"
        except Exception as e:
            return f"[drug_info] error: {e}"
        compounds = (data.get("PC_Compounds") or [])
        if not compounds:
            return f"[drug_info] no compound found for {query_label}"
        c = compounds[0]
        props = {}
        for p in (c.get("props") or []):
            urn = p.get("urn", {})
            label = urn.get("label", "")
            name_p = urn.get("name", "")
            val = p.get("value", {})
            v = val.get("sval") or val.get("ival") or val.get("fval")
            if label and v is not None:
                key = f"{label} ({name_p})" if name_p else label
                props[key] = v
        cid_val = c.get("id", {}).get("id", {}).get("cid", "?")
        lines = [f"PubChem CID: {cid_val}"]
        for k, v in list(props.items())[:20]:
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    return Tool(
        name="drug_info",
        description=(
            "Look up a drug/molecule by name, SMILES, or PubChem CID. Returns "
            "molecular formula, weight, InChI, IUPAC name, and key properties "
            "from PubChem. Provide exactly one of: name, smiles, or cid."
        ),
        parameters={"type": "object", "properties": {
            "name": _STR, "smiles": _STR, "cid": _STR}},
        func=_info, mutating=False)


# ---------------------------------------------------------------------------
# 2. ADMET property estimation (rule-based: Lipinski, Veber, Egan, Muegge)
# ---------------------------------------------------------------------------

def _drug_admet_tool() -> Tool:
    def _admet(workspace, *, smiles: str) -> str:
        if not smiles:
            return "[drug_admet] smiles is required"
        try:
            from rdkit import Chem
            from rdkit.Chem import Descriptors, Crippen, rdMolDescriptors
        except ImportError:
            return (
                "[drug_admet] rdkit not installed in this environment.\n"
                "Install: pip install rdkit\n"
                "Without rdkit, ADMET estimation is unavailable locally; "
                "consider dispatching to founder-cpu (compute_dispatch) where rdkit is available."
            )
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return f"[drug_admet] invalid SMILES: {smiles[:60]}"

        mw = Descriptors.MolWt(mol)
        logp = Crippen.MolLogP(mol)
        hba = rdMolDescriptors.CalcNumHBA(mol)
        hbd = rdMolDescriptors.CalcNumHBD(mol)
        tpsa = rdMolDescriptors.CalcTPSA(mol)
        rot = rdMolDescriptors.CalcNumRotatableBonds(mol)
        rings = rdMolDescriptors.CalcNumRings(mol)
        arom = rdMolDescriptors.CalcNumAromaticRings(mol)
        fsp3 = rdMolDescriptors.CalcFractionCSP3(mol)
        mw_heavy = Descriptors.HeavyAtomMolWt(mol)

        # Rule-based filters
        lipinski = (mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10)
        veber = (rot <= 10 and tpsa <= 140)
        egan = (tpsa <= 131.6 and logp <= 5.88)
        muegge = (200 <= mw <= 600 and -2 <= logp <= 5 and hba <= 10
                  and hbd <= 5 and tpsa <= 150 and rot <= 15 and rings <= 7)

        # Rough bioavailability (Lipinski + Veber pass → likely oral)
        oral_likely = lipinski and veber

        lines = [
            f"SMILES: {smiles[:60]}",
            "",
            "=== Physicochemical Properties ===",
            f"  Molecular weight (Da):     {mw:.2f}",
            f"  Heavy atom MW (Da):        {mw_heavy:.2f}",
            f"  LogP (lipophilicity):      {logp:.2f}",
            f"  H-bond donors:             {hbd}",
            f"  H-bond acceptors:          {hba}",
            f"  TPSA (Å²):                 {tpsa:.1f}",
            f"  Rotatable bonds:           {rot}",
            f"  Rings (total/aromatic):    {rings}/{arom}",
            f"  Fraction Csp3:             {fsp3:.2f}",
            "",
            "=== Drug-likeness Rules ===",
            f"  Lipinski Ro5:              {'PASS' if lipinski else 'FAIL'} "
            f"(MW≤500, LogP≤5, HBD≤5, HBA≤10)",
            f"  Veber (oral bioavail.):    {'PASS' if veber else 'FAIL'} "
            f"(RotBonds≤10, TPSA≤140)",
            f"  Egan (absorption):         {'PASS' if egan else 'FAIL'} "
            f"(TPSA≤131.6, LogP≤5.88)",
            f"  Muegge (lead-like):        {'PASS' if muegge else 'FAIL'}",
            "",
            "=== Assessment ===",
            f"  Oral bioavailability:      {'Likely' if oral_likely else 'Uncertain/unlikely'}",
            f"  Notes: ADMET is estimated by rule-based filters. For accurate "
            f"prediction use ML models (ADMETlab, pkCSM, SwissADME) or wet-lab assays.",
        ]
        return "\n".join(lines)

    return Tool(
        name="drug_admet",
        description=(
            "Estimate ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) "
            "properties for a molecule from its SMILES string. Applies Lipinski Ro5, "
            "Veber, Egan, and Muegge drug-likeness rules. Requires rdkit (pip install rdkit)."
        ),
        parameters={"type": "object", "properties": {"smiles": _STR}, "required": ["smiles"]},
        func=_admet, mutating=False)


# ---------------------------------------------------------------------------
# 3. Molecular similarity (Tanimoto / Morgan fingerprints)
# ---------------------------------------------------------------------------

def _drug_similarity_tool() -> Tool:
    def _sim(workspace, *, smiles_a: str, smiles_b: str, radius: int = 2) -> str:
        if not smiles_a or not smiles_b:
            return "[drug_similarity] both smiles_a and smiles_b are required"
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem, DataStructs
        except ImportError:
            return "[drug_similarity] rdkit not installed — pip install rdkit"
        mol_a = Chem.MolFromSmiles(smiles_a)
        mol_b = Chem.MolFromSmiles(smiles_b)
        if mol_a is None:
            return f"[drug_similarity] invalid SMILES A: {smiles_a[:60]}"
        if mol_b is None:
            return f"[drug_similarity] invalid SMILES B: {smiles_b[:60]}"
        fp_a = AllChem.GetMorganFingerprintAsBitVect(mol_a, radius, nBits=2048)
        fp_b = AllChem.GetMorganFingerprintAsBitVect(mol_b, radius, nBits=2048)
        tanimoto = DataStructs.TanimotoSimilarity(fp_a, fp_b)
        interp = ("very similar (scaffold overlap)" if tanimoto >= 0.85
                  else "similar" if tanimoto >= 0.6
                  else "moderate similarity" if tanimoto >= 0.4
                  else "low similarity" if tanimoto >= 0.2
                  else "dissimilar")
        return (
            f"Morgan fingerprint Tanimoto similarity (radius={radius}):\n"
            f"  A: {smiles_a[:60]}\n"
            f"  B: {smiles_b[:60]}\n"
            f"  Tanimoto: {tanimoto:.4f}  [{interp}]\n"
            f"  (0 = no overlap, 1 = identical; ≥0.4 is often considered 'similar')"
        )

    return Tool(
        name="drug_similarity",
        description=(
            "Compute Morgan fingerprint Tanimoto similarity between two molecules "
            "given as SMILES. Useful for scaffold hopping, analogue search, and "
            "clustering chemical space. radius=2 by default (ECFP4 equivalent). "
            "Requires rdkit."
        ),
        parameters={"type": "object", "properties": {
            "smiles_a": _STR, "smiles_b": _STR,
            "radius": {"type": "integer", "default": 2}},
            "required": ["smiles_a", "smiles_b"]},
        func=_sim, mutating=False)


# ---------------------------------------------------------------------------
# 4. Docking prep validator (checks receptor/ligand files before dispatching)
# ---------------------------------------------------------------------------

def _drug_docking_tool() -> Tool:
    def _dock(workspace, *, receptor_pdb: str = "", ligand_file: str = "",
              smiles: str = "", center_x: float = 0.0, center_y: float = 0.0,
              center_z: float = 0.0, box_size: float = 20.0) -> str:
        ws = Path(workspace)
        lines = ["=== Docking Run Preparation ==="]

        # Receptor check
        if receptor_pdb:
            rp = ws / receptor_pdb
            if not rp.exists():
                lines.append(f"[ERROR] receptor not found: {receptor_pdb}")
            else:
                size_kb = rp.stat().st_size // 1024
                lines.append(f"Receptor:  {receptor_pdb} ({size_kb} KB)")
                # count ATOM records
                with open(rp) as f:
                    atoms = sum(1 for l in f if l.startswith(("ATOM", "HETATM")))
                lines.append(f"           {atoms} ATOM/HETATM records")
        else:
            lines.append("Receptor:  not specified (provide receptor_pdb path in workspace)")

        # Ligand check
        if ligand_file:
            lp = ws / ligand_file
            if not lp.exists():
                lines.append(f"[ERROR] ligand file not found: {ligand_file}")
            else:
                lines.append(f"Ligand:    {ligand_file} ({lp.stat().st_size} B)")
        elif smiles:
            lines.append(f"Ligand:    SMILES provided — will need conversion to SDF/PDBQT")
            lines.append(f"           SMILES: {smiles[:80]}")
            try:
                from rdkit import Chem
                mol = Chem.MolFromSmiles(smiles)
                if mol is None:
                    lines.append("           [WARNING] SMILES failed rdkit parse — check structure")
                else:
                    from rdkit.Chem import Descriptors
                    lines.append(f"           MW={Descriptors.MolWt(mol):.1f} Da, "
                                 f"rdkit parse: OK")
            except ImportError:
                lines.append("           (rdkit not installed — SMILES validation skipped)")
        else:
            lines.append("Ligand:    not specified (provide ligand_file or smiles)")

        # Box spec
        lines.append(f"\nDocking box center: ({center_x:.1f}, {center_y:.1f}, {center_z:.1f}) Å")
        lines.append(f"Box size:           {box_size:.1f} Å")
        if center_x == 0 and center_y == 0 and center_z == 0:
            lines.append("[WARNING] center is origin — set center_x/y/z to the binding pocket "
                         "coordinates (extract from PDB or use a known active site residue centroid)")

        lines.append(
            "\n=== Next Steps ===\n"
            "1. Prepare receptor: strip water/ligands, add H with reduce/obabel, "
            "   convert to PDBQT with ADFRsuite (prepare_receptor4.py)\n"
            "2. Prepare ligand: generate 3-D coords, add H, assign charges, "
            "   convert to PDBQT (obabel or meeko)\n"
            "3. Run docking: AutoDock Vina (open-source) or Smina, "
            "   or dispatch to compute via compute_dispatch (provider=auto-gpu)\n"
            "4. Analyze: RMSD to co-crystal pose, interaction fingerprint, "
            "   score vs. known active compounds\n"
            "5. Score against PWM registry benchmark (drug_registry → pwm_standard_check)"
        )
        return "\n".join(lines)

    return Tool(
        name="drug_docking_prep",
        description=(
            "Validate inputs and generate a docking run plan for AutoDock Vina / Smina. "
            "Checks that receptor PDB and ligand file exist in the workspace; validates "
            "SMILES if provided; reminds next steps (prepare → dock → analyze → "
            "benchmark vs PWM registry). Does NOT run docking — use compute_dispatch "
            "for the actual GPU/CPU run."
        ),
        parameters={"type": "object", "properties": {
            "receptor_pdb": _STR,
            "ligand_file": _STR,
            "smiles": _STR,
            "center_x": {"type": "number", "default": 0.0},
            "center_y": {"type": "number", "default": 0.0},
            "center_z": {"type": "number", "default": 0.0},
            "box_size": {"type": "number", "default": 20.0}}},
        func=_dock, mutating=False)


# ---------------------------------------------------------------------------
# 5. PWM registry search scoped to drug-design problems
# ---------------------------------------------------------------------------

def _drug_registry_tool() -> Tool:
    _DD_KEYWORDS = ("drug", "ligand", "binding", "docking", "admet", "pharmacophore",
                    "molecular", "protein", "target", "inhibitor", "agonist", "antagonist",
                    "bioavailability", "toxicity", "kinase", "protease", "receptor",
                    "scaffold", "fragment", "lead", "hit", "affinity")

    def _search(workspace, *, query: str = "", target: str = "") -> str:
        from ai4science.harness import pwm_data
        q = " ".join(filter(None, [query, target])).strip() or "drug design molecular"
        try:
            raw = pwm_data.search(q)
        except Exception as e:
            return f"[drug_registry] PWM search error: {e}"
        # search() returns {query, principles[], specs[], benchmarks[]} — flatten
        flat = []
        for layer, label in (("principles", "principle"), ("specs", "digital-twin"),
                              ("benchmarks", "benchmark")):
            for item in (raw.get(layer) or []):
                item = dict(item)
                item.setdefault("_layer", label)
                flat.append(item)
        if not flat:
            return (f"[drug_registry] no results for '{q}' in PWM registry.\n"
                    "Tip: the drug-design domain may be sparse — consider contributing "
                    "a new principle/benchmark via pwm_contribute to earn PWM.")
        lines = [f"PWM registry results for '{q}':"]
        for r in flat[:15]:
            kind = r.get("_layer") or r.get("type") or r.get("artifact_type") or "?"
            aid = r.get("artifact_id") or r.get("id") or "?"
            title = r.get("title") or r.get("name") or "(untitled)"
            haystack = (title + " " + (r.get("description") or "")).lower()
            if not any(kw in haystack for kw in _DD_KEYWORDS):
                continue
            lines.append(f"  [{kind}] {aid}: {title}")
            if r.get("description"):
                lines.append(f"    {r['description'][:120]}")
        if len(lines) == 1:
            lines.append("  (no drug-design specific results — try a more specific query)")
        lines.append("\nUse pwm_principles / pwm_specs / pwm_benchmarks for full L1→L4 detail.")
        return "\n".join(lines)

    return Tool(
        name="drug_registry",
        description=(
            "Search the PWM registry (physicsworldmodel.org) for drug-design "
            "problems, digital twins, benchmarks, and solutions. Use query= for "
            "free-text search (e.g. 'kinase inhibitor docking') and target= for a "
            "specific protein target (e.g. 'EGFR', 'BRAF V600E'). "
            "Returns matching principles, specs, benchmarks, and solutions."
        ),
        parameters={"type": "object", "properties": {
            "query": _STR, "target": _STR}},
        func=_search, mutating=False)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def drug_design_tools() -> List[Tool]:
    return [
        _drug_info_tool(),
        _drug_admet_tool(),
        _drug_similarity_tool(),
        _drug_docking_tool(),
        _drug_registry_tool(),
    ]

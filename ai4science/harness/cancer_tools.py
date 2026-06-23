"""Cancer-domain tools for the cancer-specific agent.

Provides:
  cancer_gene_info     — look up a gene's cancer role via NCBI Entrez + ClinVar
  cancer_variant       — classify a somatic variant (oncogene / TSG / VUS)
  cancer_pathways      — list known oncogenic pathways and their key drivers
  cancer_trials        — search ClinicalTrials.gov for open oncology trials
  cancer_registry      — search PWM registry for cancer problems and solutions
"""
from __future__ import annotations

import json
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import List

from ai4science.harness.tools.base import Tool

_STR = {"type": "string"}

# TCGA / OncoKB color codes for clinical significance
_ONCOGENIC_SIGNIFICANCE = {
    "oncogenic": "activates pro-growth pathway",
    "likely oncogenic": "probable gain-of-function",
    "resistance": "resistance to therapy",
    "likely neutral": "not classified as driver",
    "vus": "variant of uncertain significance",
    "tumor suppressor": "loss-of-function / LOH",
}

# Frequently mutated genes and their primary cancer roles (curated mini-table)
_GENE_ROLES = {
    "TP53":  ("tumor_suppressor", "Most frequently mutated gene in human cancer; "
              "loss leads to failure of G1/S checkpoint and apoptosis."),
    "KRAS":  ("oncogene", "RAS-family GTPase; hotspot mutations (G12D/V/C) lock it "
              "in GTP-bound state → constitutive MAPK/PI3K signaling."),
    "BRCA1": ("tumor_suppressor", "Homologous recombination repair; germline mutations "
              "predispose to breast and ovarian cancer."),
    "BRCA2": ("tumor_suppressor", "HR repair; similar predisposition to BRCA1."),
    "EGFR":  ("oncogene", "Receptor tyrosine kinase; activating mutations/amplification "
              "common in NSCLC (L858R, exon 19 del). Target of gefitinib/erlotinib/osimertinib."),
    "BRAF":  ("oncogene", "Serine/threonine kinase; V600E hotspot activates MAPK. "
              "Target of vemurafenib/dabrafenib in melanoma/CRC."),
    "PIK3CA":("oncogene", "Catalytic subunit of PI3K; H1047R/E545K activate AKT/mTOR."),
    "PTEN":  ("tumor_suppressor", "Lipid phosphatase opposing PI3K; loss → AKT hyperactivation."),
    "MYC":   ("oncogene", "Transcription factor amplified in many cancers; drives "
              "proliferation, ribosome biogenesis, and metabolism."),
    "CDK4":  ("oncogene", "Cyclin-dependent kinase; amplification or activating mutations "
              "drive cell cycle entry."),
    "RB1":   ("tumor_suppressor", "Retinoblastoma protein; loss releases E2F → S-phase entry."),
    "ALK":   ("oncogene", "Fusion kinase (EML4-ALK in NSCLC); target of crizotinib/alectinib."),
    "RET":   ("oncogene", "Receptor tyrosine kinase; fusions in papillary thyroid cancer, NSCLC."),
    "FGFR1": ("oncogene", "FGFR kinase; amplification/fusion in bladder cancer, breast cancer."),
    "IDH1":  ("oncogene", "Metabolic enzyme; R132H neomorphic mutation produces 2-HG → "
              "epigenetic dysregulation in glioma / AML."),
    "ARID1A":("tumor_suppressor", "SWI/SNF chromatin remodeling; loss common in ovarian "
              "clear cell and endometrial cancer."),
    "VHL":   ("tumor_suppressor", "E3 ubiquitin ligase subunit; loss stabilizes HIF-1α "
              "→ pseudohypoxia in clear-cell RCC."),
}


# ---------------------------------------------------------------------------
# 1. Gene info
# ---------------------------------------------------------------------------

def _cancer_gene_info_tool() -> Tool:
    def _info(workspace, *, gene: str) -> str:
        if not gene:
            return "[cancer_gene_info] gene symbol is required (e.g. 'TP53', 'KRAS')"
        sym = gene.strip().upper()
        lines = [f"=== Cancer Gene Profile: {sym} ==="]

        # Curated mini-table
        if sym in _GENE_ROLES:
            role, desc = _GENE_ROLES[sym]
            lines.append(f"Role:        {role.replace('_', ' ').title()}")
            lines.append(f"Description: {desc}")
        else:
            lines.append("Role:        not in curated table — see NCBI/OncoKB for detail")

        # NCBI Entrez Gene (public, no key)
        try:
            url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                   f"?db=gene&term={urllib.parse.quote(sym)}[Gene+Name]+AND+Homo+sapiens[Organism]"
                   f"&retmode=json&retmax=1")
            with urllib.request.urlopen(url, timeout=8) as r:
                data = json.loads(r.read())
            ids = data.get("esearchresult", {}).get("idlist", [])
            if ids:
                gene_id = ids[0]
                sum_url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                           f"?db=gene&id={gene_id}&retmode=json")
                with urllib.request.urlopen(sum_url, timeout=8) as r2:
                    summary = json.loads(r2.read())
                rec = (summary.get("result") or {}).get(gene_id, {})
                lines.append(f"\nNCBI Gene ID: {gene_id}")
                lines.append(f"Full name:    {rec.get('description', '?')}")
                chrom = rec.get("chromosome", "?")
                loc = rec.get("maplocation", "?")
                lines.append(f"Locus:        chr{chrom} ({loc})")
                summ = (rec.get("summary") or "")[:400]
                if summ:
                    lines.append(f"Summary:      {summ}")
        except Exception as e:
            lines.append(f"\n(NCBI lookup failed: {e})")

        lines.append(f"\nResources:\n"
                     f"  OncoKB:   https://www.oncokb.org/gene/{sym}\n"
                     f"  COSMIC:   https://cancer.sanger.ac.uk/gene/overview?ln={sym}\n"
                     f"  ClinVar:  https://www.ncbi.nlm.nih.gov/clinvar/?term={sym}[gene]")
        return "\n".join(lines)

    return Tool(
        name="cancer_gene_info",
        description=(
            "Look up a gene's role in cancer: oncogene vs. tumor suppressor, "
            "key hotspot mutations, associated cancer types, and NCBI Gene info. "
            "Covers TP53, KRAS, BRCA1/2, EGFR, BRAF, PIK3CA, and more."
        ),
        parameters={"type": "object", "properties": {"gene": _STR}, "required": ["gene"]},
        func=_info, mutating=False)


# ---------------------------------------------------------------------------
# 2. Somatic variant classifier
# ---------------------------------------------------------------------------

def _cancer_variant_tool() -> Tool:
    _HOTSPOTS = {
        ("KRAS", "G12D"), ("KRAS", "G12V"), ("KRAS", "G12C"), ("KRAS", "G13D"),
        ("BRAF", "V600E"), ("BRAF", "V600K"),
        ("TP53", "R175H"), ("TP53", "R248W"), ("TP53", "R273H"),
        ("EGFR", "L858R"), ("EGFR", "T790M"),
        ("PIK3CA", "H1047R"), ("PIK3CA", "E545K"),
        ("IDH1", "R132H"), ("IDH2", "R140Q"),
    }

    def _classify(workspace, *, gene: str, mutation: str, cancer_type: str = "") -> str:
        if not gene or not mutation:
            return "[cancer_variant] gene and mutation are required (e.g. gene=KRAS mutation=G12D)"
        sym = gene.strip().upper()
        mut = mutation.strip()
        key = (sym, mut)
        lines = [f"=== Variant Classification: {sym} {mut} ==="]
        if cancer_type:
            lines[0] += f"  (cancer: {cancer_type})"

        # Hotspot check
        if key in _HOTSPOTS:
            role = _GENE_ROLES.get(sym, ("unknown", ""))[0]
            lines.append(f"Classification: ONCOGENIC HOTSPOT")
            lines.append(f"Gene role:      {role.replace('_', ' ').title()}")
            lines.append(f"Significance:   Recurrently mutated in human tumors; "
                         f"likely gain-of-function driver")
        else:
            role, _ = _GENE_ROLES.get(sym, ("unknown", ""))
            if role == "tumor_suppressor":
                lines.append("Classification: Likely loss-of-function (tumor suppressor context)")
                lines.append("Note:           Frameshift / nonsense mutations in TSG → "
                             "haploinsufficiency or LOH. Missense classification requires "
                             "structure-based or functional evidence.")
            elif role == "oncogene":
                lines.append("Classification: VUS in oncogene context")
                lines.append("Note:           Not a known hotspot; verify with OncoKB or "
                             "COSMIC mutation frequency.")
            else:
                lines.append("Classification: VUS (variant of uncertain significance)")
                lines.append("Note:           Gene not in curated table; use OncoKB / "
                             "ClinVar / CADD for pathogenicity prediction.")

        # Therapy hints
        therapy_hints = {
            "KRAS": "KRAS G12C → sotorasib/adagrasib (FDA-approved); G12D/V → investigational",
            "BRAF": "BRAF V600E → vemurafenib+cobimetinib or dabrafenib+trametinib",
            "EGFR": "EGFR L858R/exon19del → osimertinib; T790M → osimertinib (3rd gen)",
            "PIK3CA": "→ alpelisib (PI3K inhibitor, HR+/HER2- breast cancer)",
            "ALK": "→ alectinib/brigatinib (ALK+ NSCLC)",
            "RET": "→ selpercatinib/pralsetinib",
            "IDH1": "→ ivosidenib (AML), olutasidenib",
        }
        if sym in therapy_hints:
            lines.append(f"\nTherapy hint: {therapy_hints[sym]}")

        lines.append(f"\nVerify at:\n"
                     f"  OncoKB:  https://www.oncokb.org/gene/{sym}/{mut}\n"
                     f"  COSMIC:  https://cancer.sanger.ac.uk/cosmic/mutation/overview?id=\n"
                     f"  ClinVar: https://www.ncbi.nlm.nih.gov/clinvar/?term={sym}+{mut}")
        return "\n".join(lines)

    return Tool(
        name="cancer_variant",
        description=(
            "Classify a somatic mutation as oncogenic hotspot, likely driver, or VUS. "
            "Checks known hotspot tables (KRAS G12x, BRAF V600E, TP53 R175H, EGFR L858R, "
            "etc.) and gives targeted therapy hints where applicable. "
            "Provide gene (HGNC symbol) and mutation in HGVS/amino-acid format (e.g. G12D)."
        ),
        parameters={"type": "object", "properties": {
            "gene": _STR, "mutation": _STR, "cancer_type": _STR},
            "required": ["gene", "mutation"]},
        func=_classify, mutating=False)


# ---------------------------------------------------------------------------
# 3. Oncogenic pathway map
# ---------------------------------------------------------------------------

def _cancer_pathways_tool() -> Tool:
    _PATHWAYS = {
        "RAS/MAPK": {
            "drivers": ["KRAS", "NRAS", "HRAS", "BRAF", "MEK1/MAP2K1", "ERK"],
            "cancers": ["CRC", "NSCLC", "melanoma", "pancreatic"],
            "drugs": ["vemurafenib", "dabrafenib", "trametinib", "cobimetinib", "sotorasib"],
            "description": "Growth-factor → RAS → RAF → MEK → ERK proliferation cascade.",
        },
        "PI3K/AKT/mTOR": {
            "drivers": ["PIK3CA", "PTEN", "AKT1", "TSC1", "TSC2", "MTOR"],
            "cancers": ["breast", "endometrial", "glioblastoma", "RCC"],
            "drugs": ["everolimus", "alpelisib", "idelalisib", "copanlisib"],
            "description": "Survival/metabolism pathway; PTEN loss is the most common activating event.",
        },
        "p53 / Cell cycle": {
            "drivers": ["TP53", "MDM2", "RB1", "CDKN2A", "CDK4", "CDK6", "CCND1"],
            "cancers": ["pan-cancer (TP53 >50%)", "liposarcoma (MDM2 amp)"],
            "drugs": ["palbociclib", "ribociclib", "abemaciclib", "milademetan (MDM2i)"],
            "description": "G1/S checkpoint guardian; loss allows unchecked proliferation.",
        },
        "RTK / growth factors": {
            "drivers": ["EGFR", "ERBB2", "MET", "ALK", "RET", "FGFR1-4", "PDGFRA"],
            "cancers": ["NSCLC", "breast (HER2)", "gastric", "thyroid"],
            "drugs": ["osimertinib", "trastuzumab", "crizotinib", "alectinib", "selpercatinib"],
            "description": "Receptor tyrosine kinases; mutations/amplifications drive proliferation.",
        },
        "WNT/β-catenin": {
            "drivers": ["APC", "CTNNB1", "AXIN1", "RNF43"],
            "cancers": ["CRC", "hepatocellular", "endometrial"],
            "drugs": ["WNT974 (porcupine inhibitor, investigational)"],
            "description": "Embryonic development pathway reactivated in cancer.",
        },
        "Notch": {
            "drivers": ["NOTCH1", "NOTCH2", "JAG1", "DLL3"],
            "cancers": ["T-ALL", "NSCLC", "triple-negative breast"],
            "drugs": ["rovalpituzumab (DLL3-ADC)", "gamma-secretase inhibitors"],
            "description": "Cell fate / differentiation; NOTCH1 mutations frequent in T-ALL.",
        },
        "Hedgehog": {
            "drivers": ["PTCH1", "SMO", "GLI1", "GLI2"],
            "cancers": ["basal cell carcinoma", "medulloblastoma"],
            "drugs": ["vismodegib", "sonidegib"],
            "description": "Developmental pathway; SMO activating mutations drive BCC.",
        },
        "DNA Damage Response": {
            "drivers": ["BRCA1", "BRCA2", "ATM", "CHEK2", "RAD51", "PALB2"],
            "cancers": ["breast", "ovarian", "pancreatic", "prostate"],
            "drugs": ["olaparib", "rucaparib", "niraparib", "talazoparib"],
            "description": "HR deficiency creates synthetic lethality with PARP inhibitors.",
        },
        "Epigenetic": {
            "drivers": ["IDH1", "IDH2", "DNMT3A", "TET2", "EZH2", "ARID1A", "KDM6A"],
            "cancers": ["AML", "glioma", "follicular lymphoma", "DLBCL"],
            "drugs": ["ivosidenib (IDH1)", "enasidenib (IDH2)", "tazemetostat (EZH2)"],
            "description": "Chromatin/epigenome remodeling altered in hematologic and solid tumors.",
        },
        "Immune checkpoint": {
            "drivers": ["CD274/PD-L1", "PDCD1LG2/PD-L2", "TMB-high", "MSI-H"],
            "cancers": ["melanoma", "NSCLC", "TNBC", "MSI-H pan-cancer"],
            "drugs": ["pembrolizumab", "nivolumab", "atezolizumab", "ipilimumab"],
            "description": "Tumor immune evasion via PD-1/PD-L1 or CTLA-4 axis.",
        },
    }

    def _pathways(workspace, *, pathway: str = "", gene: str = "") -> str:
        if gene:
            g = gene.strip().upper()
            matches = [(name, info) for name, info in _PATHWAYS.items()
                       if any(g in d.upper() for d in info["drivers"])]
            if not matches:
                return (f"Gene '{g}' not found in pathway driver tables.\n"
                        f"Available pathways: {', '.join(_PATHWAYS)}")
            lines = [f"Pathways involving {g}:"]
            for name, info in matches:
                lines.append(f"\n  {name}")
                lines.append(f"    Drivers: {', '.join(info['drivers'])}")
                lines.append(f"    Cancers: {', '.join(info['cancers'])}")
                lines.append(f"    Drugs:   {', '.join(info['drugs'])}")
                lines.append(f"    Note:    {info['description']}")
            return "\n".join(lines)

        if pathway:
            # fuzzy match
            matches = {k: v for k, v in _PATHWAYS.items()
                       if pathway.lower() in k.lower()}
            if not matches:
                return (f"No pathway matching '{pathway}'. "
                        f"Available: {', '.join(_PATHWAYS)}")
        else:
            matches = _PATHWAYS  # list all

        lines = ["=== Oncogenic Pathway Compendium ==="]
        for name, info in matches.items():
            lines.append(f"\n{name}")
            lines.append(f"  Drivers: {', '.join(info['drivers'])}")
            lines.append(f"  Cancers: {', '.join(info['cancers'])}")
            lines.append(f"  Drugs:   {', '.join(info['drugs'])}")
            lines.append(f"  Note:    {info['description']}")
        return "\n".join(lines)

    return Tool(
        name="cancer_pathways",
        description=(
            "List oncogenic signaling pathways (RAS/MAPK, PI3K/AKT/mTOR, p53/cell cycle, "
            "RTK, WNT, Notch, Hedgehog, DDR, epigenetic, immune checkpoint) with key "
            "driver genes, associated cancer types, and approved/investigational drugs. "
            "Filter by pathway= (partial name) or gene= (HGNC symbol)."
        ),
        parameters={"type": "object", "properties": {"pathway": _STR, "gene": _STR}},
        func=_pathways, mutating=False)


# ---------------------------------------------------------------------------
# 4. ClinicalTrials.gov search
# ---------------------------------------------------------------------------

def _cancer_trials_tool() -> Tool:
    def _trials(workspace, *, query: str, cancer_type: str = "",
                phase: str = "", status: str = "RECRUITING") -> str:
        terms = " AND ".join(filter(None, [query, cancer_type]))
        params = {
            "query.term": terms,
            "filter.overallStatus": status,
            "fields": "NCTId,BriefTitle,Phase,LeadSponsorName,StartDate,Condition",
            "pageSize": "10",
            "format": "json",
        }
        if phase:
            params["filter.phase"] = phase.upper()
        url = ("https://clinicaltrials.gov/api/v2/studies?"
               + urllib.parse.urlencode(params))
        try:
            with urllib.request.urlopen(url, timeout=12) as r:
                data = json.loads(r.read())
        except Exception as e:
            return f"[cancer_trials] ClinicalTrials.gov API error: {e}"
        studies = data.get("studies") or []
        if not studies:
            return (f"[cancer_trials] no {status.lower()} trials found for '{terms}'. "
                    "Try broader terms or status='NOT_YET_RECRUITING'.")
        lines = [f"ClinicalTrials.gov — {status} trials for '{terms}' "
                 f"(showing {len(studies)} of {data.get('totalCount', '?')}):"]
        for s in studies:
            proto = s.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_m = proto.get("statusModule", {})
            design = proto.get("designModule", {})
            nct = ident.get("nctId", "?")
            title = ident.get("briefTitle", "?")[:100]
            phases = design.get("phases", [])
            phase_str = "/".join(phases) if phases else "?"
            sponsor = proto.get("sponsorCollaboratorsModule", {}).get(
                "leadSponsor", {}).get("name", "?")
            start = status_m.get("startDateStruct", {}).get("date", "?")
            lines.append(f"\n  {nct} [{phase_str}] {title}")
            lines.append(f"    Sponsor: {sponsor}  |  Start: {start}")
            lines.append(f"    https://clinicaltrials.gov/study/{nct}")
        return "\n".join(lines)

    return Tool(
        name="cancer_trials",
        description=(
            "Search ClinicalTrials.gov for open oncology clinical trials. "
            "query= is the treatment/drug/target (e.g. 'KRAS G12C', 'CAR-T', 'PARP inhibitor'); "
            "cancer_type= narrows by indication (e.g. 'NSCLC', 'glioblastoma'); "
            "phase= filters by trial phase (PHASE1, PHASE2, PHASE3); "
            "status= defaults to RECRUITING. Returns NCT IDs, title, sponsor, and links."
        ),
        parameters={"type": "object", "properties": {
            "query": _STR, "cancer_type": _STR,
            "phase": _STR, "status": {"type": "string", "default": "RECRUITING"}},
            "required": ["query"]},
        func=_trials, mutating=False)


# ---------------------------------------------------------------------------
# 5. PWM registry search scoped to cancer problems
# ---------------------------------------------------------------------------

def _cancer_registry_tool() -> Tool:
    _CANCER_KW = ("cancer", "tumor", "tumour", "oncology", "oncogenic", "carcinoma",
                  "leukemia", "lymphoma", "melanoma", "glioma", "mutation", "biomarker",
                  "survival", "prognosis", "genomic", "sequencing", "tcga", "expression",
                  "immunotherapy", "checkpoint", "driver", "metastasis")

    def _search(workspace, *, query: str = "", cancer_type: str = "") -> str:
        from ai4science.harness import pwm_data
        q = " ".join(filter(None, [query, cancer_type])).strip() or "cancer genomics"
        try:
            raw = pwm_data.search(q)
        except Exception as e:
            return f"[cancer_registry] PWM search error: {e}"
        # search() returns {query, principles[], specs[], benchmarks[]} — flatten
        flat = []
        for layer, label in (("principles", "principle"), ("specs", "digital-twin"),
                              ("benchmarks", "benchmark")):
            for item in (raw.get(layer) or []):
                item = dict(item)
                item.setdefault("_layer", label)
                flat.append(item)
        if not flat:
            return (f"[cancer_registry] no results for '{q}' in PWM registry.\n"
                    "The cancer domain may be sparse — consider contributing a new "
                    "principle/benchmark via pwm_contribute to earn PWM.")
        lines = [f"PWM registry results for '{q}':"]
        for r in flat[:15]:
            kind = r.get("_layer") or r.get("type") or r.get("artifact_type") or "?"
            aid = r.get("artifact_id") or r.get("id") or "?"
            title = r.get("title") or r.get("name") or "(untitled)"
            haystack = (title + " " + (r.get("description") or "")).lower()
            if not any(kw in haystack for kw in _CANCER_KW):
                continue
            lines.append(f"  [{kind}] {aid}: {title}")
            if r.get("description"):
                lines.append(f"    {r['description'][:120]}")
        if len(lines) == 1:
            lines.append("  (no cancer-specific results — try a broader query or 'genomics')")
        lines.append("\nUse pwm_principles / pwm_benchmarks for full L1→L4 registry detail.")
        return "\n".join(lines)

    return Tool(
        name="cancer_registry",
        description=(
            "Search the PWM registry (physicsworldmodel.org) for cancer-related "
            "physics-world-model problems, benchmarks, and solutions. Use query= for "
            "free-text (e.g. 'tumor growth model', 'survival prediction') and "
            "cancer_type= for a specific indication (e.g. 'NSCLC', 'AML')."
        ),
        parameters={"type": "object", "properties": {
            "query": _STR, "cancer_type": _STR}},
        func=_search, mutating=False)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def cancer_tools() -> List[Tool]:
    return [
        _cancer_gene_info_tool(),
        _cancer_variant_tool(),
        _cancer_pathways_tool(),
        _cancer_trials_tool(),
        _cancer_registry_tool(),
    ]

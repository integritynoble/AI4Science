"""Where the real data lives, and what happens when it is not there.

The five benchmarks began synthetic. Synthetic was honest while it lasted — each
one exercised its field's characteristic failure — but a synthetic benchmark
measures a method against a problem someone invented, and no field is moved by
that.

**A missing corpus refuses; it never falls back.** This is the whole module. A
benchmark that quietly substitutes synthetic data when the real corpus is absent
produces numbers that look like results and are not, and the person reading them
has no way to tell. So `require()` raises, and the message says exactly which
command fetches what is missing.

**A licence that must be accepted is accepted by a person, not by an agent.**
Where `needs_agreement` is set, `require()` names the dataset and stops; there is
deliberately no code path that clicks through an agreement on the owner's behalf.

That flag has to be set on the evidence, though, and not on a guess. Both
Kvasir-Capsule and the Mayo low-dose CT collection were marked here as needing
one, and neither does — CC BY 4.0 and the TCIA public terms respectively. An
over-cautious flag is not the safe default it looks like: it leaves open data
unused and it teaches the reader that the flag means nothing.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

#: corpus key -> (stat stamp, content digest). Per process; see `Corpus.digest`.
_DIGESTS: Dict[str, Tuple[Any, str]] = {}

#: Override with AI4SCIENCE_DATA. Kept outside the repo: data is not source.
DEFAULT_ROOT = Path(os.environ.get("AI4SCIENCE_DATA",
                                   Path.home() / ".ai4science" / "data"))


class CorpusMissing(FileNotFoundError):
    """The real data is not on this machine. Carries how to get it."""


@dataclass(frozen=True)
class Corpus:
    """One real dataset, and how it is obtained."""

    key: str
    title: str
    #: Files that must exist under the corpus directory for it to count as here.
    required: Tuple[str, ...]
    source: str
    licence: str
    #: True when a human must accept terms before download. No agent may.
    needs_agreement: bool = False
    fetch: str = ""
    approx_size: str = ""

    def dir(self, root: Optional[Path] = None) -> Path:
        return Path(root or DEFAULT_ROOT) / self.key

    def present(self, root: Optional[Path] = None) -> bool:
        d = self.dir(root)
        return all((d / f).exists() for f in self.required)

    def missing(self, root: Optional[Path] = None) -> Tuple[str, ...]:
        d = self.dir(root)
        return tuple(f for f in self.required if not (d / f).exists())

    def digest(self, root: Optional[Path] = None) -> str:
        """What this corpus IS, right now, as content rather than as a path.

        A generated benchmark depends on three things: the generator, the seed,
        and the data the generator reads. The first two were in the seed cache's
        key and this one was not, so re-fetching a corpus left every cached seed
        untouched — and the cache went on serving problems built from data that
        no longer existed. It is not a hypothetical: the TCGA fetcher was fixed
        to stop dropping living patients, the cohort went from 196 cases to 499,
        and seeds 0-3 kept returning their old numbers to the last digit while
        seeds 4-11 returned new ones. The same night's results were half from one
        cohort and half from another.

        Content, not mtime: a corpus copied between machines keeps its bytes and
        loses its timestamps, and two machines with the same bytes should share a
        key. All seven corpora hash in 0.12s together, so this is memoised for
        tidiness rather than out of need."""
        d = self.dir(root)
        if not d.is_dir():
            return "absent"
        stamp = tuple(sorted((str(f.relative_to(d)), f.stat().st_size,
                              f.stat().st_mtime_ns)
                             for f in d.rglob("*") if f.is_file()))
        memo = _DIGESTS.get(self.key)
        if memo is not None and memo[0] == stamp:
            return memo[1]
        h = hashlib.sha256()
        for rel, _sz, _mt in stamp:
            h.update(rel.encode())
            h.update((d / rel).read_bytes())
        out = h.hexdigest()[:16]
        _DIGESTS[self.key] = (stamp, out)
        return out

    def require(self, root: Optional[Path] = None) -> Path:
        if self.present(root):
            return self.dir(root)
        d = self.dir(root)
        lines = ["%s is not on this machine." % self.title,
                 "  expected under: %s" % d,
                 "  missing:        %s" % ", ".join(self.missing(root)),
                 "  source:         %s" % self.source,
                 "  licence:        %s" % self.licence]
        if self.approx_size:
            lines.append("  size:           %s" % self.approx_size)
        if self.needs_agreement:
            lines.append("  ** this dataset requires a person to accept its terms. "
                         "An agent may not accept them on your behalf, so nothing "
                         "here will fetch it automatically. **")
        if self.fetch:
            lines.append("  fetch:          %s" % self.fetch)
        lines.append("  This benchmark refuses to run rather than substituting "
                     "synthetic data, which would produce numbers that look like "
                     "results and are not.")
        raise CorpusMissing("\n".join(lines))


# --------------------------------------------------------------- the corpora

FETCH = "python3 -m ai4science.harness.agents.research_agents.runners.fetch %s"

TCGA_SURVIVAL = Corpus(
    key="tcga-survival",
    title="TCGA clinical survival (LUAD development, LUSC external)",
    required=("dev.json", "ext.json"),
    source="GDC Data Portal API — api.gdc.cancer.gov",
    licence="open access clinical data; NIH GDC terms",
    fetch=FETCH % "tcga-survival",
    approx_size="~2 MB",
)

DUDE = Corpus(
    key="dude",
    title="DUD-E actives and property-matched decoys",
    required=("targets.json",),
    source="dude.docking.org",
    licence="free for academic use",
    fetch=FETCH % "dude",
    approx_size="~40 MB for the target subset used here",
)

OPENKBP = Corpus(
    key="open-kbp",
    title="OpenKBP — AAPM 2020 knowledge-based planning challenge",
    required=("index.json",),
    source="github.com/ababier/open-kbp",
    licence="CC BY 4.0",
    fetch=FETCH % "open-kbp",
    approx_size="~1 GB",
)

KVASIR_CAPSULE = Corpus(
    key="kvasir-capsule",
    title="Kvasir-Capsule — wireless capsule endoscopy",
    required=("frames.npz", "metadata.json"),
    source="osf.io/dv2ag — Simula",
    # CC BY 4.0: attribution, satisfied by the provenance record written beside
    # the data. This was previously flagged as needing a person to accept terms,
    # which was wrong — it is the same open licence as OpenKBP, which was
    # fetched here without hesitation. Being cautious about a licence is right;
    # being cautious about the wrong licence just leaves real data unused.
    licence="CC BY 4.0 — attribution required, no agreement to accept",
    fetch=FETCH % "kvasir-capsule",
    approx_size="~420 MB for the classes used here",
)

LDCT = Corpus(
    key="ldct",
    title="LDCT — real paired full-dose and low-dose reconstructions",
    required=("volumes.npz", "metadata.json"),
    source="TCIA — LDCT-and-Projection-data, the paired Mayo/AAPM collection",
    licence="TCIA data usage policy",
    fetch=FETCH % "ldct",
    approx_size="~200 MB for the slice subset used here",
)

CAVE = Corpus(
    key="cave-hyperspectral",
    title="CAVE multispectral — real 512x512x31 hyperspectral scenes",
    required=("scenes.npz", "metadata.json"),
    source="cave.cs.columbia.edu — Columbia CAVE multispectral database",
    licence="free for research use, with attribution",
    fetch=FETCH % "cave-hyperspectral",
    approx_size="~100 MB for the scene subset used here",
)

METHYLATION_AGE = Corpus(
    key="methylation-age",
    title="GEO GSE40279 — whole-blood methylation with chronological age",
    required=("betas.npy", "age.npy", "site.npy", "cpg_ids.json", "metadata.json"),
    source="GEO GSE40279 (Hannum 2013) — 656 whole-blood samples, Illumina 450k",
    licence="GEO public; no agreement required",
    fetch=FETCH % "methylation-age",
    approx_size="~1.1 GB downloaded, ~55 MB stored",
)

ALL: Dict[str, Corpus] = {c.key: c for c in
                          (TCGA_SURVIVAL, DUDE, OPENKBP, KVASIR_CAPSULE, LDCT,
                           CAVE, METHYLATION_AGE)}


def status(root: Optional[Path] = None) -> str:
    L = ["real corpora under %s" % (root or DEFAULT_ROOT), ""]
    for c in ALL.values():
        state = "present" if c.present(root) else (
            "MISSING — needs a person to accept terms" if c.needs_agreement
            else "missing")
        L.append("  %-16s %-46s %s" % (c.key, c.title[:46], state))
    return "\n".join(L)

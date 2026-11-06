# Corpus link check

UTC date: 2026-11-06  
Checker and offline tests commit: `a9555f6fa5a32d271e37bc443b36fd72ac02d408`

## Dead, unavailable, or changed-size probes

- **DUD-E ampc actives:** timed out after 20 seconds; availability is unconfirmed.
- **GEO GSE40279 metadata:** timed out after 20 seconds; availability is unconfirmed.
- **GDC cases:** returned HTTP 400 to the initial probe, whose query was incomplete. The checker now builds the project filter used by the fetcher, but that corrected probe was not run live, so GDC availability remains unconfirmed.
- **OpenKBP train-pats/pt_1/ct.csv:** 1,153,464 bytes versus the corpus estimate of ~1 GB.
- **Kvasir OSF metadata.csv:** 4,050,677 bytes versus the corpus estimate of ~420 MB.
- **TCIA getCollectionValues:** 5,055 bytes versus the corpus estimate of ~200 MB.
- **CAVE balloons_ms archive:** 12,532,814 bytes versus the corpus estimate of ~100 MB.

The size differences compare an individual endpoint response with `Corpus.approx_size`, which describes the selected corpus subset. They are reported for review and do not by themselves establish that a source changed. Redirect targets below are shown without hostnames to keep this report free of host information.

## Results

| Corpus | Endpoint | HTTP status | Content length | `Corpus.approx_size` | Redirect target | Result |
|---|---|---:|---:|---|---|---|
| tcga-survival | GDC cases | 400 | 130 | ~2 MB | Same URL | Probe query incomplete; corrected query not checked live |
| dude | DUD-E ampc actives | Timeout | Unknown | ~40 MB for the target subset used here | Unknown | Availability unconfirmed |
| open-kbp | Train-pats patient 1 CT file | 200 | 1,153,464 | ~1 GB | Same URL | Size difference |
| kvasir-capsule | OSF metadata.csv | 200 | 4,050,677 | ~420 MB for the classes used here | Same URL | Size difference |
| ldct | TCIA collection values | 200 | 5,055 | ~200 MB for the slice subset used here | Same URL | Size difference |
| cave-hyperspectral | CAVE balloons_ms archive | 200 | 12,532,814 | ~100 MB for the scene subset used here | Same URL | Size difference |
| methylation-age | GEO GSE40279 metadata | Timeout | Unknown | ~1.1 GB downloaded, ~55 MB stored | Unknown | Availability unconfirmed |
| methylation-age | GEO GSE40279 beta archive | 200 | 1,223,258,643 | ~1.1 GB downloaded, ~55 MB stored | Same URL | Responded; size within tolerance |

The live check ran once. It used sequential HEAD requests with one-second spacing and a 20-second timeout; no data body was fetched and no licence or agreement was accepted. The initial run surfaced false-positive static licence warnings for explicit “no agreement” wording. The checker was corrected, and the committed offline suite verifies the static metadata check. The specified offline tests pass: 6 passed.

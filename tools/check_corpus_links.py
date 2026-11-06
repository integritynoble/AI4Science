#!/usr/bin/env python3
"""Check the registered research corpora's source links without downloading data."""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Optional

from ai4science.harness.agents.research_agents.runners import corpus
from ai4science.harness.agents.research_agents.runners.fetch import runners

USER_AGENT = "AI4Science corpus link checker/1.0"
TIMEOUT = 20
_last_request = 0.0


@dataclass(frozen=True)
class Probe:
    status: Optional[int]
    content_length: Optional[int]
    target: Optional[str]
    error: Optional[str] = None
    agreement: bool = False
    content_type: Optional[str] = None


def _request(url: str, method: str, headers: dict[str, str]) -> Probe:
    """Make one bounded HTTP request; only read a byte for a range fallback."""
    global _last_request
    delay = 1.0 - (time.monotonic() - _last_request)
    if _last_request and delay > 0:
        time.sleep(delay)
    req = urllib.request.Request(url, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            status = response.status
            length = _content_length(response.headers.get("Content-Length"))
            content_type = response.headers.get("Content-Type")
            target = response.geturl()
            if method == "GET":
                response.read(1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        length = _content_length(exc.headers.get("Content-Length")) if exc.headers else None
        content_type = exc.headers.get("Content-Type") if exc.headers else None
        target = exc.geturl()
        exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        _last_request = time.monotonic()
        reason = getattr(exc, "reason", exc)
        return Probe(None, None, None, "%s: %s" % (type(reason).__name__, reason))
    _last_request = time.monotonic()
    agreement = (bool(re.search(r"\b(agreement|consent|licen[cs]e|terms[-_/ ]of[-_/ ]use)\b",
                                (target or "").lower()))
                or bool(content_type and "text/html" in content_type.lower()))
    return Probe(status, length, target, agreement=agreement, content_type=content_type)


def _content_length(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def check_url(url: str) -> Probe:
    """Probe a URL with HEAD, falling back to a one-byte ranged GET if refused."""
    result = _request(url, "HEAD", {"User-Agent": USER_AGENT})
    if result.status in (403, 405, 501):
        result = _request(url, "GET", {
            "User-Agent": USER_AGENT,
            "Range": "bytes=0-0",
        })
    return result


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    url: str
    size: str


def sources() -> list[Source]:
    all_corpora = corpus.ALL
    return [
        Source("tcga-survival", "GDC cases", runners._GDC + "?" + urllib.parse.urlencode({
                   "filters": json.dumps({"op": "in", "content": {
                       "field": "project.project_id", "value": ["TCGA-LUAD"]}}),
                   "fields": "submitter_id", "size": "1", "format": "JSON"}),
               all_corpora["tcga-survival"].approx_size),
        Source("dude", "DUD-E ampc actives", runners._DUDE % ("ampc", "actives_final.ism"),
               all_corpora["dude"].approx_size),
        Source("open-kbp", "OpenKBP train-pats/pt_1/ct.csv",
               runners._KBP_RAW % ("train-pats", 1, "ct.csv"),
               all_corpora["open-kbp"].approx_size),
        Source("kvasir-capsule", "Kvasir OSF metadata.csv",
               runners._OSF % "metadata.csv", all_corpora["kvasir-capsule"].approx_size),
        Source("ldct", "TCIA getCollectionValues",
               runners._TCIA % "getCollectionValues" + "?Collection=LDCT-and-Projection-data",
               all_corpora["ldct"].approx_size),
        Source("cave-hyperspectral", "CAVE balloons_ms archive",
               runners._CAVE % "balloons_ms", all_corpora["cave-hyperspectral"].approx_size),
        Source("methylation-age", "GEO GSE40279 metadata", runners._GEO_META,
               all_corpora["methylation-age"].approx_size),
        Source("methylation-age", "GEO GSE40279 beta archive", runners._GEO_BETA,
               all_corpora["methylation-age"].approx_size),
    ]


def _size_bytes(value: str) -> Optional[int]:
    match = re.search(r"([\d.]+)\s*(KB|MB|GB|TB)\b", value, re.I)
    if not match:
        return None
    return int(float(match.group(1)) * 1000 ** ("KB MB GB TB".split().index(match.group(2).upper()) + 1))


def _size_mismatch(content_length: Optional[int], estimate: str) -> bool:
    expected = _size_bytes(estimate)
    return (content_length is not None and expected is not None
            and not (expected / 2 <= content_length <= expected * 2))


def _static_errors() -> list[str]:
    errors = []
    agreement_terms = re.compile(
        r"(?<!no )\b(agreement|consent|accept(?:ance)? required|must accept)\b", re.I)
    for c in corpus.ALL.values():
        if not c.source.strip():
            errors.append("%s has an empty source" % c.key)
        if not c.licence.strip():
            errors.append("%s has an empty licence" % c.key)
        if not c.needs_agreement and agreement_terms.search(c.licence):
            errors.append("%s licence mentions an agreement but needs_agreement is False" % c.key)
    return errors


def _status(probe: Probe) -> str:
    if probe.error:
        return "TIMEOUT/ERROR (%s)" % probe.error
    return str(probe.status)


def run() -> int:
    static_errors = _static_errors()
    rows = []
    dead = []
    for source in sources():
        result = check_url(source.url)
        mismatch = _size_mismatch(result.content_length, source.size)
        is_dead = result.error is not None or result.status is None or result.status >= 400
        flags = []
        if is_dead:
            flags.append("DEAD")
            dead.append(source.name)
        if mismatch:
            flags.append("SIZE MISMATCH")
        if result.agreement:
            flags.append("AGREEMENT PAGE; no terms accepted")
        rows.append((source, result, mismatch, ", ".join(flags) or "OK"))

    flagged = [row for row in rows if row[3] != "OK"]
    print("# Corpus link check")
    print("\nUTC date: %s" % time.strftime("%Y-%m-%d", time.gmtime()))
    if static_errors:
        print("\nStatic check failures: " + "; ".join(static_errors))
    if flagged:
        print("\n## Dead or changed sources")
        for source, result, _, flag in flagged:
            print("- **%s — %s**: %s (content-length %s; expected %s; %s)" % (
                source.key, source.name, flag,
                result.content_length if result.content_length is not None else "unknown",
                source.size or "unspecified", _status(result)))
    print("\n## Sources")
    print("| Corpus | Endpoint | HTTP status | Content length | Corpus.approx_size | Redirect target | Check |")
    print("|---|---|---:|---:|---|---|---|")
    for source, result, mismatch, flag in rows:
        # Omit hostnames from this public report; retain a useful endpoint label.
        target = "same URL"
        if result.target and result.target != source.url:
            parsed = urllib.parse.urlsplit(result.target)
            target = parsed.path or "/"
            if parsed.query:
                target += "?" + parsed.query
            target = "redirected to " + target
        if result.agreement:
            target += " (agreement page)"
        length = str(result.content_length) if result.content_length is not None else "unknown"
        print("| %s | %s | %s | %s | %s | %s | %s |" % (
            source.key, source.name, _status(result), length, source.size or "unspecified", target, flag))
    print("\nProbe method: HEAD; refused HEAD requests use GET with Range bytes=0-0. "
          "Requests are sequential, rate-limited to one per second, and never accept terms.")
    if dead or static_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())

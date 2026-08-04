"""Fetch the real corpora, one at a time, by name.

    python3 -m ai4science.harness.agents.research_agents.runners.fetch <key>
    python3 -m ...runners.fetch --status

Each fetcher writes a compact, self-describing bundle under the corpus root and
nothing else. Two rules hold across all of them:

  * **Provenance travels with the data.** Every bundle carries where it came
    from, when, and under what licence, so a number computed from it can be
    traced back to a source rather than to a directory someone once populated.
  * **A fetcher never accepts terms.** Where a dataset requires an agreement, the
    fetcher prints what to read and stops. Accepting a licence is a person's act.
"""
from __future__ import annotations

import sys

from .. import corpus as _corpus


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("--status", "-s"):
        print(_corpus.status())
        return 0
    key = argv[0]
    if key not in _corpus.ALL:
        print("unknown corpus %r — have: %s" % (key, ", ".join(_corpus.ALL)))
        return 2
    from . import runners as _r
    fn = getattr(_r, key.replace("-", "_"), None)
    if fn is None:
        print("no fetcher implemented for %r yet" % key)
        return 2
    out = fn(argv[1:])
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

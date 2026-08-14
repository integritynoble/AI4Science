"""`python3 -m ai4science.harness.acp` — what acpx spawns."""
from __future__ import annotations

import sys

from ai4science.harness.acp.server import serve

if __name__ == "__main__":
    sys.exit(serve())

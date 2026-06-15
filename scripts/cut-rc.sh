#!/usr/bin/env bash
# Cut a release candidate (Part A §A.5): reset `rc` to the current main commit,
# stamp X.Y.ZrcN in ai4science/__init__.py, tag vX.Y.Z-rcN, push rc + tag.
# Testers then: AI4SCIENCE_CHANNEL=rc curl …/install.sh | bash  (or `update --rc`).
#   scripts/cut-rc.sh 0.6.1 1      → 0.6.1rc1
set -euo pipefail
VER="${1:?usage: cut-rc.sh <X.Y.Z> <rcN>}"; N="${2:?rcN}"
RCVER="${VER}rc${N}"; TAG="v${VER}-rc${N}"
cd "$(cd "$(dirname "$0")/.." && pwd)"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || { echo "✗ must be on main"; exit 1; }
git diff --quiet && git diff --cached --quiet || { echo "✗ working tree dirty"; exit 1; }
echo "▸ running tests…"; python3 -m pytest -q || { echo "✗ tests failed — fix before cutting"; exit 1; }
git branch -f rc HEAD && git checkout -q rc
sed -i "s/^__version__ = .*/__version__ = \"${RCVER}\"/" ai4science/__init__.py
git commit -aqm "rc: ${TAG}"
git tag -a "$TAG" -m "$TAG"
git push -f origin rc && git push origin "$TAG"
git checkout -q main
echo "✓ cut ${RCVER} on rc (tag ${TAG}). Promote with scripts/promote-stable.sh ${VER} after approval."

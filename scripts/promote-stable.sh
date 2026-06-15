#!/usr/bin/env bash
# Promote the current rc → stable (Part A §A.5). In CI this runs inside the
# env-gated release.yml after a manager approves; locally it's the finalize step.
# Drops the rc marker (X.Y.ZrcN → X.Y.Z), tags vX.Y.Z, fast-forwards `stable`,
# then opens the next dev cycle (X.Y.(Z+1).dev0) on main.
#   scripts/promote-stable.sh 0.6.1
set -euo pipefail
VER="${1:?usage: promote-stable.sh <X.Y.Z>}"; TAG="v${VER}"
cd "$(cd "$(dirname "$0")/.." && pwd)"
git fetch -q origin
git checkout -q rc && git reset --hard -q origin/rc
sed -i "s/^__version__ = .*/__version__ = \"${VER}\"/" ai4science/__init__.py
git commit -aqm "release: ${TAG}"
git tag -a "$TAG" -m "$TAG"
git branch -f stable HEAD
git push origin stable && git push origin "$TAG"
# open the next dev cycle on main
git checkout -q main && git pull -q --ff-only origin main
nxt="$(python3 -c "v='${VER}'.split('.'); v[-1]=str(int(v[-1])+1); print('.'.join(v)+'.dev0')")"
sed -i "s/^__version__ = .*/__version__ = \"${nxt}\"/" ai4science/__init__.py
git commit -aqm "chore: open ${nxt%.dev0} dev cycle" && git push origin main
echo "✓ released ${TAG} → stable; main now ${nxt}"

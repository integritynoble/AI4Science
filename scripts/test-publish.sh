#!/usr/bin/env bash
# Local TestPyPI dry-run: build → twine check → upload to TestPyPI → (optional)
# install-back to verify. Use this before a real PyPI release.
#
#   TESTPYPI_API_TOKEN=pypi-… scripts/test-publish.sh [git-ref]
#       git-ref  optional — build that ref in a throwaway worktree (e.g. `stable`,
#                a tag). Default: the current working tree.
#       A4S_VERIFY=1  also install the uploaded build back from TestPyPI and run
#                     `ai4science version`.
#
# Token: $TESTPYPI_API_TOKEN (an https://test.pypi.org token) or a ~/.pypirc
# [testpypi] section. Real PyPI publishing is release.yml (gated); this is TEST only.
set -euo pipefail
REF="${1:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${A4S_PYTHON:-python3}"

# Build location: a throwaway worktree for a ref, else the current tree.
work="$ROOT"
if [ -n "$REF" ]; then
  work="$(mktemp -d)"
  # --detach checks out the ref's COMMIT (not the branch), so it never conflicts
  # with that branch being checked out in another worktree.
  git -C "$ROOT" worktree add -q --detach "$work" "$REF"
  trap 'git -C "$ROOT" worktree remove --force "$work" 2>/dev/null || true' EXIT
fi
cd "$work"

ver="$(grep -m1 '^__version__' ai4science/__init__.py | sed 's/.*"\(.*\)".*/\1/')"
echo "▸ building pwm-ai4science ${ver}${REF:+ (ref $REF)}"
rm -rf dist build
"$PY" -m pip install -q build twine
"$PY" -m build
"$PY" -m twine check dist/*

if [ -z "${TESTPYPI_API_TOKEN:-}" ] && [ ! -f "$HOME/.pypirc" ]; then
  echo "✗ no TESTPYPI_API_TOKEN and no ~/.pypirc — create a token at https://test.pypi.org/manage/account/token/"
  exit 1
fi
echo "▸ uploading ${ver} to TestPyPI (--skip-existing)…"
if [ -n "${TESTPYPI_API_TOKEN:-}" ]; then
  TWINE_USERNAME=__token__ TWINE_PASSWORD="$TESTPYPI_API_TOKEN" \
    "$PY" -m twine upload --repository-url https://test.pypi.org/legacy/ --skip-existing dist/*
else
  "$PY" -m twine upload --repository testpypi --skip-existing dist/*
fi
echo "✓ uploaded pwm-ai4science ${ver} to TestPyPI"

if [ "${A4S_VERIFY:-0}" = "1" ]; then
  echo "▸ verifying install-back from TestPyPI…"
  v="$(mktemp -d)"; "$PY" -m venv "$v/venv"
  "$v/venv/bin/pip" install -q --upgrade pip
  # deps not on TestPyPI come from real PyPI via --extra-index-url
  "$v/venv/bin/pip" install -q \
    --index-url https://test.pypi.org/simple/ \
    --extra-index-url https://pypi.org/simple/ \
    "pwm-ai4science==${ver}"
  echo -n "  install-back: "; "$v/venv/bin/ai4science" version
  rm -rf "$v"
fi
echo "Done. Verify manually: pip install --index-url https://test.pypi.org/simple/ \\"
echo "  --extra-index-url https://pypi.org/simple/ 'pwm-ai4science[claude]==${ver}'"

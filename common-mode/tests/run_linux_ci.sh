#!/bin/sh
# Every common-mode check that runs on Linux, CI style: no real model calls, loopback fixtures only.
#   sh common-mode/tests/run_linux_ci.sh OUTPUT_DIR
# Downloads the pinned engine and ripgrep once (checked against the committed locks) into OUTPUT_DIR/cache;
# set AI4SCIENCE_CI_CACHE to reuse a cache folder. strace (smoke --trace) and pwsh steps run when installed.
set -eu
tests=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
source=$(dirname "$tests")
out=${1:?usage: run_linux_ci.sh OUTPUT_DIR}
mkdir -p "$out"
out=$(CDPATH= cd -- "$out" && pwd -P)
cache=${AI4SCIENCE_CI_CACHE:-$out/cache}
mkdir -p "$cache"
step() { printf '\n== %s\n' "$*"; }

step static checks
for f in "$source/install.sh" "$source/ai4science" "$tests/run_linux_ci.sh"; do sh -n "$f"; done
python3 -m json.tool "$source/defaults.json" >/dev/null
python3 - "$source" <<'EOF'
import sys
from pathlib import Path
root = Path(sys.argv[1])
for p in sorted(root.glob('*.ps1')) + sorted(root.glob('*.cmd')):
    bad = [i for i, b in enumerate(p.read_bytes()) if b > 127]
    assert not bad, f'{p.name}: non-ASCII bytes (Windows PowerShell 5.1 reads scripts as ANSI)'
for line in (root / 'artifacts.lock').read_text().splitlines():
    name, digest, url = line.split(' ')
    assert len(digest) == 128 and url.startswith('https://registry.npmjs.org/') and url.endswith('.tgz'), line
for line in (root / 'ripgrep.lock').read_text().splitlines():
    name, digest, url = line.split(' ')
    assert len(digest) == 64 and url.startswith('https://github.com/BurntSushi/ripgrep/releases/'), line
print('ascii, lock formats: ok')
EOF
python3 -m py_compile "$tests"/*.py
if command -v pwsh >/dev/null 2>&1; then
  for f in "$source"/*.ps1; do
    pwsh -NoLogo -NoProfile -Command "\$t=\$null;\$e=\$null;[void][System.Management.Automation.Language.Parser]::ParseFile('$f',[ref]\$t,[ref]\$e); if (\$e.Count) { \$e | ForEach-Object { \$_.ToString() }; exit 1 }"
  done
  echo 'PowerShell parse: ok'
fi

step pinned downloads
python3 - "$source" "$cache" <<'EOF'
import hashlib, sys, urllib.request
from pathlib import Path
source, cache = Path(sys.argv[1]), Path(sys.argv[2])
def get(lock, key, algorithm, name):
    for line in (source / lock).read_text().splitlines():
        k, digest, url = line.split(' ')
        if k == key:
            dest = cache / name
            if not dest.exists() or hashlib.new(algorithm, dest.read_bytes()).hexdigest() != digest:
                urllib.request.urlretrieve(url, dest)
            assert hashlib.new(algorithm, dest.read_bytes()).hexdigest() == digest, name
            return
    raise SystemExit(f'{key} missing in {lock}')
get('artifacts.lock', 'opencode-linux-x64-baseline', 'sha512', 'engine-linux-x64.tgz')
get('ripgrep.lock', 'linux-x64', 'sha256', 'ripgrep-linux-x64.tgz')
get('ripgrep.lock', 'windows-x64', 'sha256', 'ripgrep-windows-x64.zip')
print('cache ok')
EOF

step launcher environment '(stub engine)'
python3 "$tests/launcher_environment.py" --output "$out/launcher"

step install and first-session isolation
python3 "$tests/install_isolation.py" --source "$source" --output "$out/isolation" \
  --engine-archive "$cache/engine-linux-x64.tgz" --ripgrep-archive "$cache/ripgrep-linux-x64.tgz"
prefix="$out/isolation/prefix with spaces"

step workspace sessions '(E4 common arm, serve)'
python3 "$tests/workspace_session.py" --prefix "$prefix" --output "$out/workspace"

step smoke
if command -v strace >/dev/null 2>&1; then trace=--trace; else trace=; echo 'strace not installed: smoke runs without network tracing'; fi
python3 "$tests/smoke.py" "$prefix" $trace --output "$out/smoke"

if command -v pwsh >/dev/null 2>&1; then
  step install.ps1 and ai4science.ps1 under pwsh
  python3 "$tests/install_ps1_on_linux.py" --output "$out/powershell" \
    --engine-archive "$cache/engine-linux-x64.tgz" --ripgrep-archive "$cache/ripgrep-windows-x64.zip"
else
  step 'install.ps1 skipped: pwsh not installed'
fi
printf '\nALL COMMON-MODE LINUX CHECKS PASSED\n'

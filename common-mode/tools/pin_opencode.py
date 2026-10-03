#!/usr/bin/env python3
"""Re-pin the OpenCode engine: rewrite artifacts.lock and opencode.version from npm's published integrity data.

  python3 common-mode/tools/pin_opencode.py 1.18.35        # then: sh common-mode/tests/run_linux_ci.sh DIR

Only these two files change. Each lock line is "<package> <sha512 hex> <tarball URL>", taken from the registry's
`dist.integrity` (sha512) and `dist.tarball` for that exact version. ripgrep.lock is separate and unchanged.
After re-pinning, review the upstream changes to the hooks the launcher relies on (see README "Isolation").
"""
import base64
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ['opencode-linux-x64-baseline', 'opencode-linux-x64-baseline-musl', 'opencode-linux-arm64',
            'opencode-linux-arm64-musl', 'opencode-darwin-x64-baseline', 'opencode-darwin-arm64',
            'opencode-windows-x64-baseline', 'opencode-windows-arm64']


def record(package, version):
    with urllib.request.urlopen(f'https://registry.npmjs.org/{package}/{version}', timeout=60) as r:
        dist = json.load(r)['dist']
    algorithm, b64 = dist['integrity'].split('-', 1)
    if algorithm != 'sha512':
        raise SystemExit(f'{package}@{version}: integrity is {algorithm}, need sha512')
    url = dist['tarball']
    if not url.startswith('https://registry.npmjs.org/'):
        raise SystemExit(f'{package}@{version}: unexpected tarball URL {url}')
    return f'{package} {base64.b64decode(b64).hex()} {url}'


def main(version):
    lines = [record(p, version) for p in PACKAGES]
    (ROOT / 'artifacts.lock').write_text('\n'.join(lines) + '\n')
    (ROOT / 'opencode.version').write_text(version + '\n')
    print(f'pinned OpenCode {version}: artifacts.lock ({len(lines)} packages), opencode.version')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])

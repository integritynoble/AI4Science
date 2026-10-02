#!/usr/bin/env python3
"""Run install.ps1 and ai4science.ps1 end to end with PowerShell 7 on Linux (no Windows machine needed).

This exercises the PowerShell scripts' own logic: checksum checks, unpacking, the dependency step, the version
check, then a non-interactive --workspace session against a loopback fake model (no real model call).
To run on Linux, a copy of the source gets one Windows lock line re-pointed at the pinned *Linux* engine,
repacked as package/bin/opencode.exe; powershell.exe and tar.exe are shims for pwsh and tar; ai4science.cmd
is a shell shim for ai4science.ps1. It cannot show Windows PowerShell 5.1 or Windows path behaviour:
run TESTING.md's Windows procedure for that.

  python3 common-mode/tests/install_ps1_on_linux.py --output DIR [--engine-archive TGZ] [--ripgrep-archive ZIP]
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request

from fake_openai import serve

SOURCE = Path(__file__).resolve().parents[1]


def lock_line(path, key):
    for line in path.read_text().splitlines():
        if line.split(' ')[0] == key:
            return line.split(' ')
    raise SystemExit(f'{key} not in {path.name}')


def fetch(url, dest, algorithm, digest):
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
    got = hashlib.new(algorithm, dest.read_bytes()).hexdigest()
    assert got == digest, f'{dest.name}: {algorithm} mismatch'
    return dest


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--engine-archive', type=Path, help='the pinned opencode-linux-x64-baseline tgz')
    parser.add_argument('--ripgrep-archive', type=Path, help='the pinned ripgrep windows-x64 zip')
    args = parser.parse_args()
    pwsh = shutil.which('pwsh')
    if sys.platform != 'linux' or not pwsh:
        parser.error('needs Linux and pwsh (PowerShell 7) on PATH')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)

    # Pinned inputs, checked against the committed locks.
    _, engine_sha512, engine_url = lock_line(SOURCE / 'artifacts.lock', 'opencode-linux-x64-baseline')
    engine = fetch(engine_url, args.engine_archive.resolve() if args.engine_archive else out / 'engine.tgz',
                   'sha512', engine_sha512)
    _, rg_sha256, rg_url = lock_line(SOURCE / 'ripgrep.lock', 'windows-x64')
    ripgrep = fetch(rg_url, args.ripgrep_archive.resolve() if args.ripgrep_archive else out / 'ripgrep.zip',
                    'sha256', rg_sha256)

    # The Linux engine repacked under the Windows file name.
    with tarfile.open(engine) as tin:
        binary = tin.extractfile('package/bin/opencode').read()
    fake = out / 'engine-as-windows.tgz'
    with tarfile.open(fake, 'w:gz') as tout:
        info = tarfile.TarInfo('package/bin/opencode.exe')
        info.size, info.mode = len(binary), 0o755
        tout.addfile(info, io.BytesIO(binary))
    fake_sha512 = hashlib.sha512(fake.read_bytes()).hexdigest()

    src = out / 'source'
    shutil.copytree(SOURCE, src, ignore=shutil.ignore_patterns('tests', 'evidence', '__pycache__'))
    lines = [(f'opencode-windows-x64-baseline {fake_sha512} https://invalid.example/not-downloaded.tgz'
              if line.startswith('opencode-windows-x64-baseline ') else line)
             for line in (src / 'artifacts.lock').read_text().splitlines()]
    (src / 'artifacts.lock').write_text('\n'.join(lines) + '\n')
    (src / 'ai4science.cmd').write_text('#!/bin/sh\nexec pwsh -NoLogo -NoProfile -File "$(dirname "$0")/ai4science.ps1" "$@"\n')
    (src / 'ai4science.cmd').chmod(0o755)
    shims = out / 'shims'
    shims.mkdir()
    for name, target in (('powershell.exe', pwsh), ('tar.exe', shutil.which('tar'))):
        (shims / name).write_text(f'#!/bin/sh\nexec "{target}" "$@"\n')
        (shims / name).chmod(0o755)

    home, local = out / 'home', out / 'LocalAppData'
    home.mkdir()
    local.mkdir()
    env = {'PATH': f'{shims}{os.pathsep}{os.defpath}', 'HOME': str(home), 'LANG': 'C.UTF-8', 'TERM': 'dumb',
           'LOCALAPPDATA': str(local), 'PROCESSOR_ARCHITECTURE': 'AMD64', 'TMPDIR': str(out),
           'AI4SCIENCE_ARTIFACT': str(fake), 'AI4SCIENCE_RIPGREP_ARTIFACT': str(ripgrep),
           'OPENCODE_CONFIG_CONTENT': '{"model":"hostile/x"}'}
    prefix = local / 'AI4Science' / 'Common Test'
    done = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-File', str(src / 'install.ps1'), '-Prefix', str(prefix)],
                          env=env, cwd=home, capture_output=True, text=True, timeout=600)
    (out / 'install.stdout').write_text(done.stdout)
    (out / 'install.stderr').write_text(done.stderr)
    assert done.returncode == 0, f'install.ps1 exit {done.returncode}; see install.stderr'
    assert done.stdout.strip().splitlines()[-1] == f'Installed. Add this directory to PATH: {prefix / "bin"}'
    config = prefix / 'var' / 'config' / 'opencode'
    assert json.loads((config / 'opencode.json').read_text()) == json.loads((SOURCE / 'defaults.json').read_text())
    assert not (config / 'install-prime.mjs').exists()
    assert (config / 'node_modules' / '@opencode-ai' / 'plugin').is_dir()
    assert (prefix / 'var' / 'cache' / 'opencode' / 'bin' / 'rg.exe').is_file()
    refused = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-File', str(src / 'install.ps1'), '-Prefix', str(prefix)],
                             env=env, cwd=home, capture_output=True, text=True, timeout=120)
    assert refused.returncode != 0 and 'already exists' in refused.stderr + refused.stdout

    # A workspace session through ai4science.ps1 with the real engine and the fake model.
    workspace = out / 'work space'
    workspace.mkdir()
    target = workspace / 'result.txt'
    model = serve(log=out / 'requests.jsonl',
                  tool_call={'name': 'write', 'arguments': {'filePath': str(target), 'content': 'PS_OK\n'}})
    threading.Thread(target=model.serve_forever, daemon=True).start()
    try:
        run_env = {**env, 'AI4SCIENCE_BASE_URL': f'http://127.0.0.1:{model.server_port}/v1'}
        session = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-File', str(prefix / 'bin' / 'ai4science.ps1'),
                                  '--workspace', str(workspace), 'run', '--format', 'json', 'Write result.txt.'],
                                 env=run_env, cwd=home, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                 timeout=240)
    finally:
        model.shutdown()
        model.server_close()
    (out / 'session.stdout').write_text(session.stdout)
    (out / 'session.stderr').write_text(session.stderr)
    assert session.returncode == 0, f'session exit {session.returncode}; see session.stderr'
    assert target.read_text() == 'PS_OK\n', 'the PowerShell-launched session did not write in its workspace'
    summary = {'install_ps1': 'passed under pwsh on Linux', 'reinstall_into_existing_prefix': 'refused',
               'ps1_workspace_session': 'file written', 'real_model_calls': 0,
               'not_covered': 'Windows PowerShell 5.1, Windows paths, ai4science.cmd, Windows engine binary'}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

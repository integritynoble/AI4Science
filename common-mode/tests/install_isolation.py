#!/usr/bin/env python3
"""Linux install + cold session regression; synthetic settings, loopback model only.

inotify records reads/writes of seeded global paths without needing strace.
This is a config isolation check, not a process-wide network sandbox proof.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from fake_openai import serve


class FileWatch:
    MASK = 0x1 | 0x2 | 0x4 | 0x20 | 0x40 | 0x80 | 0x100 | 0x200 | 0x400 | 0x800

    def __init__(self, paths):
        self.lib = ctypes.CDLL(None, use_errno=True)
        self.fd = self.lib.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_init1')
        self.paths = {}
        for path in paths:
            wd = self.lib.inotify_add_watch(self.fd, os.fsencode(path), self.MASK)
            if wd < 0:
                self.close()
                raise OSError(ctypes.get_errno(), f'inotify_add_watch: {path}')
            self.paths[wd] = str(path)

    def events(self):
        result = []
        while True:
            try:
                data = os.read(self.fd, 65536)
            except BlockingIOError:
                return result
            offset = 0
            while offset < len(data):
                wd, mask, cookie, size = struct.unpack_from('iIII', data, offset)
                name = data[offset + 16:offset + 16 + size].rstrip(b'\0').decode()
                result.append({'path': self.paths.get(wd, 'INOTIFY_OVERFLOW'),
                               'name': name, 'mask': hex(mask)})
                offset += 16 + size

    def close(self):
        os.close(self.fd)


def snapshot(root):
    result = {}
    for path in sorted(root.rglob('*')):
        value = {'mode': path.stat().st_mode}
        if path.is_file():
            value['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        result[str(path.relative_to(root))] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--engine-archive', type=Path)
    parser.add_argument('--ripgrep-archive', type=Path)
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Linux inotify is required; no unmonitored pass is allowed')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixture = out / 'fixture'
    home, project = fixture / 'home', fixture / 'project'
    home.mkdir(parents=True)
    project.mkdir()
    prefix = out / 'prefix with spaces'
    marker = out / 'MCP_MUST_NOT_START'
    trap_requests = []

    class Trap(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            trap_requests.append(self.path)
            self.send_error(500)

        do_POST = do_GET

    trap = ThreadingHTTPServer(('127.0.0.1', 0), Trap)
    model = serve(log=out / 'requests.jsonl')
    for server in (trap, model):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    trap_url = f'http://127.0.0.1:{trap.server_port}/must-not-call'
    hostile = {
        'username': 'HOSTILE_GLOBAL_MUST_NOT_LOAD', 'model': 'hostile/sentinel',
        'small_model': 'hostile/sentinel', 'enabled_providers': ['hostile'],
        'provider': {'hostile': {'npm': '@ai-sdk/openai-compatible',
                                'options': {'baseURL': trap_url, 'apiKey': 'SYNTHETIC'},
                                'models': {'sentinel': {'name': 'Hostile sentinel'}}}},
        'mcp': {'hostile': {'type': 'local', 'enabled': True,
                           'command': [sys.executable, '-c',
                                       f'from pathlib import Path; Path({str(marker)!r}).write_text("STARTED")']}}
    }
    for relative in ('.config/opencode/opencode.json', '.config/opencode/config.json',
                     '.opencode/opencode.json', 'managed/opencode.json'):
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(hostile))
    for relative in ('opencode.json', '.opencode/opencode.json'):
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(hostile))
    for relative, contents in (
        ('.local/share/opencode/auth.json', '{"hostile":{"type":"api","key":"SYNTHETIC_AUTH"}}'),
        ('.local/state/opencode/sentinel', 'SYNTHETIC_STATE'),
        ('.cache/opencode/sentinel', 'SYNTHETIC_CACHE'),
    ):
        path = home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    protected = [p for p in home.rglob('*')] + [p for p in project.rglob('*') if p.is_file()]
    before = snapshot(fixture)
    # Verify that this machine's monitor actually detects file reads.
    watch = FileWatch(protected)
    (home / '.local/share/opencode/auth.json').read_bytes()
    assert watch.events(), 'inotify read detection self-check failed'
    watch.close()
    env = {
        'PATH': os.defpath, 'HOME': str(home), 'USER': 'isolation-test',
        'LANG': 'C.UTF-8', 'TERM': 'dumb', 'NO_COLOR': '1',
        'TMPDIR': str(out),
        'XDG_CONFIG_HOME': str(home / '.config'),
        'XDG_DATA_HOME': str(home / '.local/share'),
        'XDG_CACHE_HOME': str(home / '.cache'),
        'XDG_STATE_HOME': str(home / '.local/state'),
        'AI4SCIENCE_BASE_URL': f'http://127.0.0.1:{model.server_port}/v1',
        'AI4SCIENCE_API_KEY': 'SYNTHETIC_LOCAL_KEY',
        'AI4SCIENCE_PROJECT_CONFIG': '1',  # Installer must force private mode.
        'OPENCODE_CONFIG': str(home / '.config/opencode/opencode.json'),
        'OPENCODE_CONFIG_DIR': str(home / '.config/opencode'),
        'OPENCODE_CONFIG_CONTENT': json.dumps(hostile),
        'OPENCODE_TEST_HOME': str(home),
        'OPENCODE_TEST_MANAGED_CONFIG_DIR': str(home / 'managed'),
        'OPENCODE_DB': str(home / '.local/share/opencode/hostile.db'),
        'OPENCODE_MODELS_PATH': str(home / '.cache/opencode/sentinel'),
        'OPENCODE_MODELS_URL': trap_url,
        'OPENCODE_DISABLE_PROJECT_CONFIG': '0',
        'OPENCODE_DISABLE_DEFAULT_PLUGINS': '0',
        'OPENCODE_EXPERIMENTAL': '1',
        'OPENCODE_FUTURE_HOSTILE_FLAG': 'must-not-survive',
    }
    if args.engine_archive:
        env['AI4SCIENCE_ARTIFACT'] = str(args.engine_archive.resolve())
    if args.ripgrep_archive:
        env['AI4SCIENCE_RIPGREP_ARTIFACT'] = str(args.ripgrep_archive.resolve())
    source = args.source.resolve()
    wrapper = prefix / 'bin/ai4science'
    phases = []

    def run(label, command):
        watch = FileWatch(protected)
        try:
            completed = subprocess.run(command, env=env, cwd=project, capture_output=True,
                                       text=True, timeout=180)
            events = watch.events()
        finally:
            watch.close()
        (out / f'{label}.stdout').write_text(completed.stdout)
        (out / f'{label}.stderr').write_text(completed.stderr)
        (out / f'{label}.file-events.json').write_text(json.dumps(events, indent=2))
        assert not events, f'{label}: accessed protected settings: {events}'
        assert snapshot(fixture) == before, f'{label}: changed global or project tree'
        assert not trap_requests, f'{label}: contacted hostile provider/catalog: {trap_requests}'
        assert not marker.exists(), f'{label}: started hostile MCP'
        assert completed.returncode == 0, f'{label}: exit {completed.returncode}; inspect output'
        phases.append(label)
        return completed.stdout

    try:
        run('install', ['sh', str(source / 'install.sh'), '--prefix', str(prefix)])
        env.pop('AI4SCIENCE_PROJECT_CONFIG')
        # The first inference session precedes all debug/model/version probes.
        assert not (out / 'requests.jsonl').exists(), 'install attempted inference'
        session = run('first-session', [str(wrapper), 'run', '--format', 'json',
                                      'Reply with exactly AI4SCIENCE_LOCAL_OK. Do not use tools.'])
        events = [json.loads(line) for line in session.splitlines() if line.startswith('{')]
        assert any(e.get('type') == 'text' and 'AI4SCIENCE_LOCAL_OK' in e['part']['text'] for e in events)
        assert not any(e.get('type') == 'error' for e in events), events
        config = json.loads(run('config', [str(wrapper), 'debug', 'config']))
        assert config['username'] == 'AI4Science'
        assert config['enabled_providers'] == ['own-llm']
        assert set(config['provider']) == {'own-llm'}
        assert config['mcp'] == {'pwm': {'enabled': False}}
        assert config['plugin'] == []
        assert run('models', [str(wrapper), 'models']).strip() == 'own-llm/local'
        requests = [json.loads(line) for line in (out / 'requests.jsonl').read_text().splitlines()]
        assert requests and all(r['model'] == 'local' and r['path'] == '/v1/chat/completions' for r in requests)
        summary = {'phases': phases, 'synthetic_inputs': True, 'real_model_calls': 0,
                   'local_fixture_requests': len(requests), 'hostile_requests': trap_requests,
                   'hostile_mcp_started': marker.exists(), 'protected_file_events': 0,
                   'global_and_project_tree_unchanged': True,
                   'file_monitor_self_check': 'passed', 'network_sandbox_proven': False}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
    finally:
        for server in (trap, model):
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    main()

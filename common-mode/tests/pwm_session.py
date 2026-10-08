#!/usr/bin/env python3
"""Synthetic remote configuration security checks; no remote connections or model calls."""
import argparse
import json
import os
from pathlib import Path
import pty
import secrets
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]
OUTPUT = None


class RemoteSession(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='case-', dir=OUTPUT))
        self.prefix = self.root / 'prefix with spaces'
        self.bin = self.prefix / 'bin'
        self.bin.mkdir(parents=True)
        for name in ('ai4science', 'pwm-config.py'):
            shutil.copyfile(SOURCE / name, self.bin / name)
        self.wrapper = self.bin / 'ai4science'
        self.wrapper.chmod(0o755)
        self.config = self.prefix / 'var/config/opencode/opencode.json'
        self.config.parent.mkdir(parents=True)
        self.original = (SOURCE / 'defaults.json').read_bytes()
        self.config.write_bytes(self.original)
        instruction = self.prefix / 'share/agent/pwm-loop.md'
        instruction.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / 'agent/pwm-loop.md', instruction)
        self.engine = self.bin / 'opencode'
        self.engine.write_text(f'#!{sys.executable}\nimport json, os, sys, time\n'
                               'from pathlib import Path\n'
                               'p = Path(__file__).resolve().parent.parent\n'
                               '(p / "started").write_text("yes")\n'
                               '(p / "session.log").write_text(json.dumps({"argv": sys.argv, "env": dict(os.environ)}))\n'
                               'if "hold" in sys.argv: time.sleep(30)\n'
                               'print("session completed")\n')
        self.engine.chmod(0o755)
        self.key = secrets.token_hex(24)
        self.key_path = self.prefix / 'var/pwm/key'
        self.env = {'PATH': os.defpath, 'HOME': str(self.root),
                    'AI4SCIENCE_PWM_URL': 'https://' + 'remote.invalid/mcp'}

    def tearDown(self):
        # Synthetic markers never survive in evidence files or failure reports.
        shutil.rmtree(self.root)

    def launch(self, *args, input=None, extra=None):
        return subprocess.run([str(self.wrapper), *args], env={**self.env, **(extra or {})},
                              input=input, text=True, capture_output=True, timeout=15)

    def login(self):
        result = self.launch('pwm', 'login', input=self.key + '\nignored second line\n')
        self.assertEqual(result.returncode, 0)
        self.assertTrue(self.key not in result.stdout + result.stderr, 'private value in output')
        self.assertTrue(self.key_path.read_text() == self.key, 'saved key mismatch')

    def scan_prefix(self, allowed):
        found = set()
        for path in self.prefix.rglob('*'):
            if path.is_file() and self.key.encode() in path.read_bytes():
                found.add(str(path.relative_to(self.prefix)))
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
        self.assertEqual(found, allowed)

    def test_login_reads_once_and_permissions(self):
        self.login()
        self.scan_prefix({'var/pwm/key'})
        self.assertEqual(stat.S_IMODE(self.key_path.parent.stat().st_mode), 0o700)

    def test_terminal_prompt_does_not_echo(self):
        master, slave = pty.openpty()
        child = subprocess.Popen([str(self.wrapper), 'pwm', 'login'], env=self.env,
                                 stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        received = b''
        try:
            deadline = time.monotonic() + 10
            while b'Key: ' not in received and time.monotonic() < deadline:
                if select.select([master], [], [], .1)[0]:
                    received += os.read(master, 4096)
            self.assertIn(b'Key: ', received)
            os.write(master, (self.key + '\n').encode())
            child.wait(timeout=10)
            while select.select([master], [], [], .1)[0]:
                try:
                    received += os.read(master, 4096)
                except OSError:
                    break
            self.assertEqual(child.returncode, 0)
            self.assertTrue(self.key.encode() not in received, 'private value echoed')
            self.assertTrue(self.key_path.read_text() == self.key, 'saved key mismatch')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()
            os.close(master)

    def test_opt_in_config_and_instruction_then_exact_restore(self):
        self.login()
        result = self.launch('--pwm', 'run', 'normal argument')
        self.assertEqual(result.returncode, 0)
        config = json.loads(self.config.read_text())
        remote = config['mcp']['pwm']
        self.assertEqual(remote['type'], 'remote')
        self.assertTrue(remote['enabled'])
        self.assertFalse(remote['oauth'])
        self.assertEqual(remote['url'], self.env['AI4SCIENCE_PWM_URL'])
        self.assertTrue(remote['headers']['Authorization'] == 'Bearer ' + self.key)
        self.assertEqual(config['instructions'], [str(self.prefix / 'share/agent/pwm-loop.md')])
        self.assertTrue(self.key not in result.stdout + result.stderr, 'private value in output')
        self.scan_prefix({'var/pwm/key', 'var/config/opencode/opencode.json'})
        self.assertEqual(self.launch('run').returncode, 0)
        self.assertTrue(self.config.read_bytes() == self.original, 'config bytes changed')
        self.assertNotIn('instructions', json.loads(self.config.read_text()))
        self.assertTrue(json.loads(self.config.read_text())['mcp'] == {'pwm': {'enabled': False}}, 'remote config survived restoration')
        self.scan_prefix({'var/pwm/key'})

    def test_ordinary_config_and_environment_unchanged(self):
        self.assertEqual(self.launch('run').returncode, 0)
        before = (self.prefix / 'session.log').read_bytes()
        self.login()
        self.assertEqual(self.launch('--pwm', 'run').returncode, 0)
        self.assertEqual(self.launch('run').returncode, 0)
        self.assertEqual((self.prefix / 'session.log').read_bytes(), before)
        self.assertTrue(self.config.read_bytes() == self.original, 'config bytes changed')

    def test_process_arguments_environment_and_logs(self):
        self.login()
        child = subprocess.Popen([str(self.wrapper), '--pwm', 'hold'], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not (self.prefix / 'started').exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.prefix / 'started').exists())
            checked = 0
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    command = (proc / 'cmdline').read_bytes()
                except (PermissionError, FileNotFoundError, ProcessLookupError):
                    continue
                self.assertTrue(self.key.encode() not in command, 'private value in process arguments')
                checked += 1
            self.assertGreater(checked, 0)
            self.assertTrue(self.key.encode() not in (Path('/proc') / str(child.pid) / 'environ').read_bytes(), 'private value in environment')
            ps = subprocess.run(['ps', '-eo', 'args'], capture_output=True, check=True).stdout
            self.assertTrue(self.key.encode() not in ps, 'private value in process listing')
            self.scan_prefix({'var/pwm/key', 'var/config/opencode/opencode.json'})
        finally:
            child.terminate()
            stdout, stderr = child.communicate(timeout=5)
        self.assertTrue(self.key.encode() not in stdout + stderr, 'private value in output')

    def test_missing_or_insecure_url_starts_nothing(self):
        self.login()
        for value in ('', 'http://' + 'remote.invalid/mcp', 'https://', 'https://user@remote.invalid'):
            result = self.launch('--pwm', 'run', extra={'AI4SCIENCE_PWM_URL': value})
            self.assertEqual(result.returncode, 2)
            self.assertIn('AI4SCIENCE_PWM_URL', result.stderr)
            self.assertIn('https', result.stderr)
            self.assertFalse((self.prefix / 'started').exists())
            self.assertTrue(self.config.read_bytes() == self.original, 'config bytes changed')

    def test_missing_key_and_extra_login_argument_refused(self):
        result = self.launch('--pwm', 'run')
        self.assertEqual(result.returncode, 2)
        self.assertIn('pwm login', result.stderr)
        self.assertEqual(self.launch('pwm', 'login', 'extra').returncode, 2)
        self.assertFalse((self.prefix / 'started').exists())
        self.assertFalse(self.key_path.exists())

    def test_empty_or_interpolated_key_refused(self):
        for value in ('\n', '{env:UNTRUSTED}\n', 'contains space\n'):
            self.assertEqual(self.launch('pwm', 'login', input=value).returncode, 2)
        self.assertFalse(self.key_path.exists())

    def test_logout_restores_config_and_deletes_key(self):
        self.login()
        self.assertEqual(self.launch('--pwm', 'run').returncode, 0)
        self.assertEqual(self.launch('pwm', 'logout').returncode, 0)
        self.assertFalse(self.key_path.exists())
        self.assertTrue(self.config.read_bytes() == self.original, 'config bytes changed')
        self.scan_prefix(set())
        self.assertEqual(self.launch('pwm', 'logout').returncode, 0)

    def test_hostile_environment_and_global_config_ignored(self):
        self.login()
        hostile = self.root / '.config/opencode/opencode.json'
        hostile.parent.mkdir(parents=True)
        hostile.write_text(json.dumps({'mcp': {'hostile': {'enabled': True}}, 'instructions': ['hostile.md']}))
        env = {'OPENCODE_CONFIG': str(hostile), 'OPENCODE_CONFIG_CONTENT': hostile.read_text(),
               'OPENCODE_CONFIG_DIR': str(hostile.parent), 'OPENCODE_TEST_HOME': str(self.root),
               'PYTHONPATH': str(self.root), 'PYTHONSTARTUP': str(self.root / 'hostile.py')}
        (self.root / 'hostile.py').write_text('raise RuntimeError("must not load")')
        self.assertEqual(self.launch('--pwm', 'run', extra=env).returncode, 0)
        log = json.loads((self.prefix / 'session.log').read_text())
        self.assertNotIn('OPENCODE_CONFIG_CONTENT', log['env'])
        self.assertEqual(log['env']['OPENCODE_CONFIG'], str(self.config))
        config = json.loads(self.config.read_text())
        self.assertEqual(set(config['mcp']), {'pwm'})
        self.assertEqual(len(config['instructions']), 1)
        self.assertTrue(config['mcp']['pwm']['headers']['Authorization'] == 'Bearer ' + self.key)
        self.scan_prefix({'var/pwm/key', 'var/config/opencode/opencode.json'})

    def test_workspace_flag_order_and_repeated_opt_in(self):
        self.login()
        for args in (('--pwm', '--workspace', str(self.root)), ('--workspace', str(self.root), '--pwm')):
            self.assertEqual(self.launch(*args, 'run').returncode, 0)
            self.assertEqual(len(json.loads(self.config.read_text())['instructions']), 1)
        self.assertEqual(self.launch('run').returncode, 0)
        self.assertTrue(self.config.read_bytes() == self.original, 'config bytes changed')

    def test_launch_rereads_saved_key(self):
        self.login()
        self.assertEqual(self.launch('--pwm', 'run').returncode, 0)
        replacement = secrets.token_hex(24)
        self.assertEqual(self.launch('pwm', 'login', input=replacement + '\n').returncode, 0)
        self.assertEqual(self.launch('--pwm', 'run').returncode, 0)
        stored = json.loads(self.config.read_text())['mcp']['pwm']['headers']['Authorization']
        self.assertTrue(stored == 'Bearer ' + replacement, 'launch did not reread key')
        self.assertTrue(self.key not in stored, 'previous key survived launch')

    def test_linked_storage_directory_refused(self):
        target = self.root / 'other storage'
        target.mkdir()
        self.key_path.parent.parent.mkdir(parents=True, exist_ok=True)
        self.key_path.parent.symlink_to(target)
        self.assertEqual(self.launch('pwm', 'login', input=self.key + '\n').returncode, 2)
        self.assertFalse(list(target.iterdir()))

    def test_invalid_config_error_does_not_print_private_data(self):
        self.login()
        self.config.write_text('{"invalid": "' + self.key)
        result = self.launch('--pwm', 'run')
        self.assertEqual(result.returncode, 2)
        self.assertTrue(self.key not in result.stdout + result.stderr, 'private data in validation error')
        self.assertFalse((self.prefix / 'started').exists())

    def test_symlinks_and_insecure_saved_key_fail_closed(self):
        self.login()
        self.key_path.chmod(0o644)
        self.assertEqual(self.launch('--pwm', 'run').returncode, 2)
        self.key_path.unlink()
        target = self.root / 'target'
        target.write_text('unchanged')
        self.key_path.symlink_to(target)
        self.assertEqual(self.launch('pwm', 'login', input=self.key + '\n').returncode, 2)
        self.assertEqual(target.read_text(), 'unchanged')
        self.assertFalse((self.prefix / 'started').exists())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RemoteSession)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    summary = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
               'skipped': len(result.skipped), 'synthetic_inputs': True, 'real_model_calls': 0,
               'remote_connections': 0, 'cases': [name for name in unittest.defaultTestLoader.getTestCaseNames(RemoteSession)]}
    (OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    sys.exit(0 if result.wasSuccessful() else 1)

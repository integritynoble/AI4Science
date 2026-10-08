#!/usr/bin/env python3
"""Private configuration for an optional remote MCP server (Python 3)."""
import getpass
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from urllib.parse import urlsplit


class ConfigurationError(Exception):
    pass


def fail(message):
    raise ConfigurationError(message)


def regular(path):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        fail('Unsafe private configuration path.')


def private_dir(path):
    for parent in [*reversed(path.parents), path]:
        if parent.is_symlink():
            fail('Unsafe private configuration path.')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not path.is_dir():
        fail('Unsafe private configuration path.')
    path.chmod(0o700)


def write_private(path, data):
    regular(path)
    fd, name = tempfile.mkstemp(prefix='.private-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    prefix, action = Path(sys.argv[1]), sys.argv[2]
    storage = prefix / 'var/pwm'
    config = prefix / 'var/config/opencode/opencode.json'
    key_path, baseline = storage / 'key', storage / 'base-config'
    private_dir(storage)
    for path in (key_path, baseline, config):
        for parent in path.parents:
            if parent.is_symlink():
                fail('Unsafe private configuration path.')
        regular(path)
    if action == 'login':
        value = getpass.getpass('Key: ') if sys.stdin.isatty() else sys.stdin.readline().rstrip('\r\n')
        if not value or any(ord(c) < 33 or ord(c) > 126 or c in '{}' for c in value):
            fail('A nonempty key without whitespace, control characters or braces is required.')
        write_private(key_path, value.encode())
        print('Key saved in private storage.')
        return
    if action in ('off', 'logout'):
        if baseline.exists():
            private_dir(config.parent)
            write_private(config, baseline.read_bytes())
            baseline.unlink()
        if action == 'logout':
            key_path.unlink(missing_ok=True)
            print('Key removed from private storage.')
        return
    url = os.environ.get('AI4SCIENCE_PWM_URL', '')
    try:
        parsed = urlsplit(url)
        valid = (parsed.scheme == 'https' and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.fragment and parsed.port != 0
                 and not any(c.isspace() or ord(c) < 33 or c in '{}\\' for c in url))
    except ValueError:
        valid = False
    if not valid:
        fail('AI4SCIENCE_PWM_URL must be set to an https URL for a remote MCP server.')
    if not key_path.exists():
        fail('No saved key; run ai4science pwm login first.')
    if stat.S_IMODE(key_path.stat().st_mode) != 0o600:
        fail('Saved key must have mode 0600; run ai4science pwm login again.')
    value = key_path.read_text()
    if not value or any(ord(c) < 33 or ord(c) > 126 or c in '{}' for c in value):
        fail('Saved key is invalid; run ai4science pwm login again.')
    original = baseline.read_bytes() if baseline.exists() else config.read_bytes()
    settings = json.loads(original)
    settings.setdefault('mcp', {})['pwm'] = {
        'type': 'remote', 'url': url, 'enabled': True, 'oauth': False,
        'headers': {'Authorization': 'Bearer ' + value}}
    instruction = prefix / 'share/agent/pwm-loop.md'
    if not instruction.is_file():
        fail('Remote workflow instruction is missing; reinstall the wrapper.')
    settings.setdefault('instructions', []).append(str(instruction))
    private_dir(config.parent)
    if not baseline.exists():
        write_private(baseline, original)
    write_private(config, (json.dumps(settings, indent=2) + '\n').encode())


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt):
        # Exceptions may contain private data; print only our fixed validation messages.
        error = sys.exc_info()[1]
        if isinstance(error, ConfigurationError):
            print(str(error), file=sys.stderr)
        else:
            print('Unable to prepare private remote configuration.', file=sys.stderr)
        sys.exit(2)

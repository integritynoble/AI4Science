#!/usr/bin/env python3
"""Check inherited flag removal and failed engine version propagation without a model."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    prefix = out / 'prefix with spaces'
    bin_dir = prefix / 'bin'
    bin_dir.mkdir(parents=True)
    wrapper = bin_dir / 'ai4science'
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'ai4science', wrapper)
    wrapper.chmod(0o755)
    engine = bin_dir / 'opencode'
    engine.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                      'if "--version" in sys.argv: sys.exit(17)\n'
                      'print(json.dumps({**dict(os.environ), "TEST_CWD": os.getcwd()}))\n')
    engine.chmod(0o755)
    home = out / 'home'
    home.mkdir()
    env = {'PATH': os.defpath, 'HOME': str(home),
           'OPENCODE_SERVER_PASSWORD': 'HOSTILE_PASSWORD',
           'OPENCODE_FUTURE_HOSTILE_FLAG': 'HOSTILE_FLAG',
           'OPENCODE_CONFIG_CONTENT': 'HOSTILE_CONFIG',
           'OPENCODE_TEST_HOME': str(home),
           'AI4SCIENCE_BASE_URL': 'http://127.0.0.1:12345/v1',
           'AI4SCIENCE_MODEL': 'science-test-model'}
    result = subprocess.run([str(wrapper), 'debug', 'config'], env=env, text=True,
                            capture_output=True, check=True)
    received = json.loads(result.stdout)
    for key in ['OPENCODE_SERVER_PASSWORD', 'OPENCODE_FUTURE_HOSTILE_FLAG', 'OPENCODE_CONFIG_CONTENT']:
        assert key not in received, f'inherited upstream variable survived: {key}'
    assert received['OPENCODE_TEST_HOME'] == str(prefix / 'var/home')
    assert received['OPENCODE_DISABLE_PROJECT_CONFIG'] == '1'
    assert received['AI4SCIENCE_BASE_URL'] == env['AI4SCIENCE_BASE_URL']
    assert received['AI4SCIENCE_MODEL'] == env['AI4SCIENCE_MODEL']
    assert received['TEST_CWD'] == str(prefix / 'var/config/opencode')
    env['AI4SCIENCE_PROJECT_CONFIG'] = '1'
    opted_in = subprocess.run([str(wrapper), 'debug', 'config'], cwd=home, env=env,
                              text=True, capture_output=True, check=True)
    opted_env = json.loads(opted_in.stdout)
    assert opted_env['TEST_CWD'] == str(home)
    assert opted_env['OPENCODE_DISABLE_PROJECT_CONFIG'] == '0'
    env.pop('AI4SCIENCE_PROJECT_CONFIG')
    version = subprocess.run([str(wrapper), '--version'], env=env, text=True, capture_output=True)
    assert version.returncode == 17 and not version.stdout, version
    # A missing clearing utility must fail before invoking the engine.
    for missing in ['env', 'sed']:
        path = out / ('path-without-' + missing)
        path.mkdir()
        for command in ['dirname', 'mkdir', 'uname', 'env', 'sed']:
            if command != missing:
                (path / command).symlink_to(shutil.which(command))
        restricted = {**env, 'PATH': str(path)}
        failed = subprocess.run([str(wrapper), 'debug', 'config'], env=restricted,
                                text=True, capture_output=True)
        assert failed.returncode != 0 and not failed.stdout, failed
    summary = {'unknown_and_known_upstream_flags_removed': True,
               'private_home_and_project_flag_set': True,
               'explicit_model_settings_preserved': True,
               'private_default_directory_and_explicit_project_opt_in': True,
               'failed_engine_version_exit': version.returncode,
               'missing_clearing_utilities_fail_closed': True}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

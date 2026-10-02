#!/usr/bin/env python3
"""Check inherited flag removal and failed engine version propagation without a model."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def check_powershell(out, pwsh):
    """The same contract for ai4science.ps1 (run by pwsh here; Windows PowerShell 5.1 on Windows)."""
    prefix = out / 'ps prefix with spaces'
    bin_dir = prefix / 'bin'
    bin_dir.mkdir(parents=True)
    shutil.copyfile(Path(__file__).resolve().parents[1] / 'ai4science.ps1', bin_dir / 'ai4science.ps1')
    engine = bin_dir / 'opencode.exe'
    engine.write_text(f'#!{sys.executable}\nimport json, os, sys\n'
                      'if "--version" in sys.argv: print("9.9.9"); sys.exit(0)\n'
                      'print(json.dumps({**dict(os.environ), "TEST_CWD": os.getcwd(), "TEST_ARGV": sys.argv[1:]}))\n')
    engine.chmod(0o755)
    home = out / 'ps home'
    workspace = out / 'ps work space'
    home.mkdir()
    workspace.mkdir()
    env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'OPENCODE_SERVER_PASSWORD': 'HOSTILE_PASSWORD',
           'OPENCODE_FUTURE_HOSTILE_FLAG': 'HOSTILE_FLAG', 'AI4SCIENCE_MODEL': 'science-test-model'}

    def launch(*argv, extra=None):
        return subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-File', str(bin_dir / 'ai4science.ps1'), *argv],
                              cwd=home, env={**env, **(extra or {})}, text=True, capture_output=True, timeout=60)

    got = json.loads(launch('debug', 'config').stdout)
    assert 'OPENCODE_SERVER_PASSWORD' not in got and 'OPENCODE_FUTURE_HOSTILE_FLAG' not in got
    assert got['OPENCODE_DISABLE_PROJECT_CONFIG'] == '1' and got['AI4SCIENCE_MODEL'] == 'science-test-model'
    assert Path(got['TEST_CWD']) == prefix / 'var/config/opencode', got['TEST_CWD']
    got = json.loads(launch('--workspace', str(workspace), 'run', 'two words').stdout)
    assert Path(got['TEST_CWD']) == workspace and got['OPENCODE_DISABLE_PROJECT_CONFIG'] == '1'
    assert got['TEST_ARGV'] == ['run', 'two words'], got['TEST_ARGV']
    got = json.loads(launch('debug', extra={'AI4SCIENCE_WORKSPACE': str(workspace)}).stdout)
    assert Path(got['TEST_CWD']) == workspace
    got = json.loads(launch('serve', extra={'AI4SCIENCE_SERVER_PASSWORD': 'pw'}).stdout)
    assert got['OPENCODE_SERVER_PASSWORD'] == 'pw' and 'AI4SCIENCE_SERVER_PASSWORD' not in got
    for bad in (['--workspace'], ['--workspace', str(out / 'missing'), 'run']):
        refused = launch(*bad)
        assert refused.returncode == 2 and not refused.stdout, (bad, refused)
    assert launch('upgrade').returncode == 2
    assert launch('--version').stdout.strip() == 'AI4Science common mode (OpenCode 9.9.9)'
    return True


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
    # --workspace DIR / AI4SCIENCE_WORKSPACE: the session works in DIR with project settings still off.
    workspace = out / 'work space'
    workspace.mkdir()
    for argv, extra in ((['--workspace', str(workspace)], {}), ([], {'AI4SCIENCE_WORKSPACE': str(workspace)})):
        ran = subprocess.run([str(wrapper), *argv, 'debug', 'config'], cwd=home, env={**env, **extra},
                             text=True, capture_output=True, check=True)
        got = json.loads(ran.stdout)
        assert got['TEST_CWD'] == str(workspace) and got['PWD'] == str(workspace), got['TEST_CWD']
        assert got['OPENCODE_DISABLE_PROJECT_CONFIG'] == '1'
    trusted = json.loads(subprocess.run([str(wrapper), '--workspace', str(workspace), 'debug', 'config'], cwd=home,
                                        env={**env, 'AI4SCIENCE_PROJECT_CONFIG': '1'}, text=True,
                                        capture_output=True, check=True).stdout)
    assert trusted['TEST_CWD'] == str(workspace) and trusted['OPENCODE_DISABLE_PROJECT_CONFIG'] == '0'
    for bad in (['--workspace'], ['--workspace', ''], ['--workspace', str(out / 'missing'), 'run', 'x']):
        refused = subprocess.run([str(wrapper), *bad], cwd=home, env=env, text=True, capture_output=True)
        assert refused.returncode == 2 and not refused.stdout, (bad, refused)
    # `serve` gets a password only through AI4SCIENCE_SERVER_PASSWORD, which the engine's tools do not inherit.
    served = json.loads(subprocess.run([str(wrapper), 'serve'], env={**env, 'AI4SCIENCE_SERVER_PASSWORD': 'pw'},
                                       text=True, capture_output=True, check=True).stdout)
    assert served['OPENCODE_SERVER_PASSWORD'] == 'pw' and served['OPENCODE_SERVER_USERNAME'] == 'opencode'
    assert 'AI4SCIENCE_SERVER_PASSWORD' not in served
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
               'workspace_option_keeps_project_settings_off': True,
               'server_password_only_via_ai4science_variable': True,
               'failed_engine_version_exit': version.returncode,
               'missing_clearing_utilities_fail_closed': True}
    pwsh = shutil.which('pwsh') or shutil.which('powershell')
    summary['powershell_launcher'] = check_powershell(out, pwsh) if pwsh else 'skipped: no PowerShell'
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

"""Fail closed on incomplete coverage, failed tests, or abnormal pytest termination.

Requires independent collection inventory and the captured pytest exit code.
Known-red entries are reported, but do not authorize a successful full-suite gate.
"""
from pathlib import Path
import argparse
import importlib
import json
import os
import sys
import xml.etree.ElementTree as ET

MIN_TESTS = 1000
ROOT = Path(__file__).resolve().parent.parent


def _list(name):
    path = ROOT / 'tests' / 'ci' / name
    return {l.strip() for l in path.read_text().splitlines() if l.strip() and not l.startswith('#')}


def _nodeid(case):
    cls, name = case.get('classname', ''), case.get('name', '')
    if not cls:
        return name.replace('.', '/') + '.py'
    parts = cls.split('.')
    for i in range(len(parts), 0, -1):
        mod = '/'.join(parts[:i]) + '.py'
        if (ROOT / mod).exists():
            return '::'.join([mod, *parts[i:], name])
    return f'{cls}::{name}'


def _control_plane_available():
    try:
        importlib.import_module('pwm_control_plane')
        return True
    except ImportError:
        return False


def _missing_control_plane(case, nid, modules, available):
    error = case.find('error')
    if available or nid not in modules or case.get('classname') or error is None:
        return False
    text = ''.join(error.itertext())
    # pytest represents collection failures with an empty classname. Runtime
    # AssertionError/ModuleNotFoundError entries always have a test node ID.
    return (error.get('message') == 'collection failure'
            and 'ModuleNotFoundError' in text
            and ("No module named 'pwm_control_plane'" in text
                 or "No module named 'pwm_control_plane." in text))


def main(report, manifest=None, pytest_exit=None):
    problems = []
    try:
        if manifest is None or pytest_exit is None:
            raise ValueError('collection manifest and pytest exit status are required')
        inventory = json.loads(Path(manifest).read_text())
        expected_list = inventory['nodeids']
        if not isinstance(expected_list, list) or not all(isinstance(n, str) for n in expected_list):
            raise ValueError('invalid collection inventory')
        expected = set(expected_list)
        if len(expected) != len(expected_list):
            problems.append('duplicate IDs in collection inventory')
        if inventory['exit'] not in (0, 1):
            problems.append(f"abnormal collection termination: {inventory['exit']}")
        code = int(Path(pytest_exit).read_text().strip())
        if code not in (0, 1):
            problems.append(f'abnormal pytest termination: {code}')
        cases = list(ET.parse(report).getroot().iter('testcase'))
    except (OSError, ValueError, KeyError, TypeError, ET.ParseError) as exc:
        print(f'FAIL: missing or invalid test evidence: {exc}')
        return 1
    known, cp_modules = _list('known_red.txt'), _list('needs_control_plane.txt')
    cp_available = _control_plane_available()  # environment flags cannot assert importability
    seen, executed, passed, skipped, bad, missing_cp = set(), set(), set(), set(), {}, set()
    for case in cases:
        nid = _nodeid(case)
        if nid in seen:
            problems.append(f'duplicate JUnit ID: {nid}')
        seen.add(nid)
        failure, error = case.find('failure'), case.find('error')
        if failure is not None or error is not None:
            if _missing_control_plane(case, nid, cp_modules, cp_available):
                missing_cp.add(nid)
            else:
                bad[nid] = (failure if failure is not None else error).get('message', '')[:200]
            if case.get('classname'):
                executed.add(nid)
        elif case.find('skipped') is not None:
            skipped.add(nid)
        else:
            executed.add(nid)
            passed.add(nid)
    reported_tests = {n for n in seen if '::' in n}
    missing = expected - reported_tests
    extra = reported_tests - expected
    if missing:
        problems.append(f'{len(missing)} collected tests missing from JUnit: ' + ', '.join(sorted(missing)[:10]))
    if extra:
        problems.append(f'{len(extra)} uncollected tests in JUnit: ' + ', '.join(sorted(extra)[:10]))
    if len(executed) < MIN_TESTS:
        problems.append(f'only {len(executed)} unique executed tests (< {MIN_TESTS})')
    if skipped:
        problems.append(f'{len(skipped)} skipped tests: full coverage is incomplete')
    if missing_cp or not cp_available:
        problems.append('private-dependency coverage INCOMPLETE: pwm_control_plane unavailable or modules not collected')
    if inventory['exit'] != 0:
        problems.append('independent collection did not complete successfully')
    if code != 0:
        problems.append(f'pytest reported failure (exit {code})')
    if bad:
        problems.append(f'{len(bad)} failed/errored cases, including known-red failures')
    lines = [f'## Full-suite gate: {"FAIL" if problems else "PASS"}',
             f'- {len(passed)} passed, {len(bad)} failed/errored, {len(skipped)} skipped; {len(executed)} unique executed',
             f'- control plane importable: {cp_available}',
             '- NOT RUN (demonstrated missing-package collection errors): ' + (', '.join(sorted(missing_cp)) or 'none'),
             '- known-red still failing (requires owner policy decision): ' + (', '.join(sorted(set(bad) & known)) or 'none'),
             '- known-red now passing: ' + (', '.join(sorted(passed & known)) or 'none')]
    lines += [f'- {p}' for p in problems]
    lines += [f'- `{n}`: {bad[n]}' for n in sorted(bad)]
    text = '\n'.join(lines)
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(text + '\n')
    return int(bool(problems))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', nargs='?', default='junit.xml')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--pytest-exit', required=True)
    args = parser.parse_args()
    sys.exit(main(args.report, args.manifest, args.pytest_exit))

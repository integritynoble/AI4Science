"""Gate CI on the JUnit report, not on pytest's exit code.

Fails when: the report is missing or ran too few tests; any test fails or
errors that is not listed in tests/ci/known_red.txt; or a control-plane module
errors while the control plane IS installed. Known-red tests that still fail,
known-red tests that now pass, and control-plane modules not run are all
printed (and written to the GitHub job summary) every time.

    python scripts/ci_gate.py junit.xml
"""
from pathlib import Path
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
    if not cls:                                   # a collection error: name is the dotted module
        return name.replace('.', '/') + '.py'
    parts = cls.split('.')
    for i in range(len(parts), 0, -1):            # tests.a.test_b[.TestClass] -> tests/a/test_b.py
        mod = '/'.join(parts[:i]) + '.py'
        if (ROOT / mod).exists():
            return '::'.join([mod, *parts[i:], name])
    return f'{cls}::{name}'


def main(report):
    if not Path(report).exists():
        print(f'no JUnit report at {report}: the suite did not run'); return 1
    cases = list(ET.parse(report).getroot().iter('testcase'))
    known, cp_modules = _list('known_red.txt'), _list('needs_control_plane.txt')
    cp_installed = os.environ.get('CONTROL_PLANE') == '1'
    bad, passed, skipped = {}, set(), 0
    for c in cases:
        nid = _nodeid(c)
        if c.find('failure') is not None or c.find('error') is not None:
            bad[nid] = (c.find('failure') if c.find('failure') is not None else c.find('error')).get('message', '')[:200]
        elif c.find('skipped') is not None:
            skipped += 1
        else:
            passed.add(nid)
    still_red = sorted(n for n in bad if n in known)
    now_green = sorted(n for n in known if n in passed)
    not_run = sorted(n for n in bad if n.split('::')[0] in cp_modules and not cp_installed and n not in known)
    unexpected = sorted(n for n in bad if n not in known and n not in not_run)
    lines = [f'## Test suite: {len(passed)} passed, {len(bad)} failed/errored, {skipped} skipped '
             f'({len(cases)} total)',
             f'- control plane installed: {"yes" if cp_installed else "NO (CONTROL_PLANE_READ_TOKEN unset)"}',
             f'- known-red, still failing ({len(still_red)}): ' + (', '.join(still_red) or 'none'),
             f'- known-red, NOW PASSING — remove from tests/ci/known_red.txt ({len(now_green)}): '
             + (', '.join(now_green) or 'none'),
             f'- NOT RUN, need pwm_control_plane ({len(not_run)}): ' + (', '.join(not_run) or 'none'),
             f'- UNEXPECTED failures ({len(unexpected)}):'] + [f'  - `{n}`: {bad[n]}' for n in unexpected]
    too_few = len(cases) < MIN_TESTS
    if too_few:
        lines.append(f'- only {len(cases)} tests in the report (< {MIN_TESTS}): treating as a broken run')
    text = '\n'.join(lines)
    print(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as f:
            f.write(text + '\n')
    return 1 if unexpected or too_few else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'junit.xml'))

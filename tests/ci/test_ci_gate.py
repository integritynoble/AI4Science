"""Synthetic JUnit regressions for coverage and termination fail-closed behavior."""
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

spec = importlib.util.spec_from_file_location('ci_gate', Path(__file__).parents[2] / 'scripts/ci_gate.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    monkeypatch.setattr(gate, '_control_plane_available', lambda: True)
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)
    ci = tmp_path / 'tests/ci'
    ci.mkdir(parents=True)
    (ci / 'known_red.txt').write_text('tests/test_sample.py::test_0\n')
    (ci / 'needs_control_plane.txt').write_text('tests/test_sample.py\n')
    (tmp_path / 'tests/test_sample.py').write_text('')

    def run(*, count=1000, kind='pass', duplicate=False, omitted=False, code=0,
            collection_code=0, extra=None, manifest=True):
        suite = ET.Element('testsuite')
        ids = [f'tests/test_sample.py::test_{i}' for i in range(count)]
        for i in range(count - int(omitted)):
            c = ET.SubElement(suite, 'testcase', classname='tests.test_sample', name=f'test_{0 if duplicate else i}')
            if kind == 'skip':
                ET.SubElement(c, 'skipped', message='not run')
            elif kind == 'failure' and i == 0:
                ET.SubElement(c, 'failure', message='AssertionError')
        if extra:
            attrs, tag, message, text = extra
            c = ET.SubElement(suite, 'testcase', **attrs)
            ET.SubElement(c, tag, message=message).text = text
        report, inventory, status = (tmp_path / n for n in ('junit.xml', 'collection.json', 'exit.txt'))
        ET.ElementTree(suite).write(report)
        inventory.write_text(json.dumps({'nodeids': ids, 'exit': collection_code}))
        status.write_text(str(code))
        return gate.main(report, inventory if manifest else None, status)
    return run


def test_complete_unique_run_passes(evidence):
    assert evidence() == 0


@pytest.mark.parametrize('settings', [
    {'kind': 'skip'}, {'duplicate': True}, {'omitted': True}, {'count': 999},
    {'code': 2}, {'code': 3}, {'code': 4}, {'code': 5},
    {'collection_code': 2}, {'collection_code': 1}, {'manifest': False},
    {'kind': 'failure'}, {'code': 1},
])
def test_incomplete_or_failed_evidence_never_passes(evidence, settings):
    assert evidence(**settings) == 1


def test_control_plane_runtime_assertion_is_never_exempt(evidence, monkeypatch):
    monkeypatch.setattr(gate, '_control_plane_available', lambda: False)
    extra = ({'classname': 'tests.test_sample', 'name': 'test_runtime'},
             'failure', 'AssertionError', 'ordinary runtime failure')
    assert evidence(extra=extra) == 1


def test_only_exact_missing_package_collection_error_is_classified(monkeypatch):
    modules = {'tests/test_sample.py'}
    for cls, msg, body, expected in [
        ('', 'collection failure', "ModuleNotFoundError: No module named 'pwm_control_plane'", True),
        ('', 'collection failure', "ModuleNotFoundError: No module named 'pwm_control_plane.sandbox'", True),
        ('', 'collection failure', "ModuleNotFoundError: No module named 'numpy'", False),
        ('', 'collection failure', 'AssertionError', False),
        ('tests.test_sample', 'collection failure', "ModuleNotFoundError: No module named 'pwm_control_plane'", False),
    ]:
        c = ET.Element('testcase', classname=cls)
        ET.SubElement(c, 'error', message=msg).text = body
        assert gate._missing_control_plane(c, 'tests/test_sample.py', modules, False) is expected
        assert not gate._missing_control_plane(c, 'tests/test_sample.py', modules, True)


def test_missing_private_package_is_nonpassing_even_with_env_flag(evidence, monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE', '1')
    monkeypatch.setattr(gate, '_control_plane_available', lambda: False)
    assert evidence() == 1


def test_missing_or_malformed_report_fails(tmp_path):
    assert gate.main(tmp_path / 'missing.xml') == 1
    (tmp_path / 'bad.xml').write_text('<bad')
    (tmp_path / 'inventory').write_text('{}')
    (tmp_path / 'exit').write_text('0')
    assert gate.main(tmp_path / 'bad.xml', tmp_path / 'inventory', tmp_path / 'exit') == 1


def test_env_flag_does_not_control_dependency_check(monkeypatch):
    monkeypatch.setenv('CONTROL_PLANE', '1')
    def missing(name):
        raise ModuleNotFoundError(name)
    monkeypatch.setattr(gate.importlib, 'import_module', missing)
    assert not gate._control_plane_available()

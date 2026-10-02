"""Write an independently collected test inventory for ci_gate.py."""
import json
from pathlib import Path


def pytest_addoption(parser):
    parser.addoption('--ci-manifest', required=True)


def pytest_sessionfinish(session, exitstatus):
    Path(session.config.getoption('--ci-manifest')).write_text(json.dumps({
        'nodeids': [item.nodeid for item in session.items],
        'exit': int(exitstatus),
    }, indent=2))

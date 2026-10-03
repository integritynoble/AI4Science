"""Exactly one installed distribution may provide the `ai4science` package.

On the owner's Windows PC (2026-10-03) the venv held the old pwm-ai4science 0.6.34.dev0 and pwm-agent-core
1.0.1, both shipping ai4science/, and `ai4science --version` failed. Both installers now run one helper
("clean" before installing, "check" after); these tests run that helper in a real venv with fake dists.
"""
from pathlib import Path
import os
import re
import subprocess
import sys
import venv

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper_from(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.search(r"^# ai4science-venv-helper:.*?^    sys\.exit\(.*?\)$", text, re.S | re.M)
    assert match, f"helper not found in {path.name}"
    return match.group(0) + "\n"


def test_both_installers_carry_the_same_helper():
    assert helper_from(ROOT / "install.ps1") == helper_from(ROOT / "install.sh")
    assert helper_from(ROOT / "scripts/install.ps1") == helper_from(ROOT / "install.ps1")


def test_this_environment_has_at_most_one_ai4science_provider():
    import importlib.metadata as md
    found = []
    for dist in md.distributions():
        tops = set((dist.read_text("top_level.txt") or "").split())
        tops.update(f.parts[0] for f in (dist.files or []) if f.parts)
        if "ai4science" in tops:
            found.append(f"{dist.metadata['Name']} {dist.version}")
    assert len(found) <= 1, f"two distributions provide the ai4science package: {found}"


def fake_dist(site_packages, name, version, modules):
    """A minimal installed distribution pip can uninstall (METADATA, RECORD, files)."""
    info = site_packages / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")
    (info / "INSTALLER").write_text("pip\n")
    tops = sorted({m.split("/")[0] for m in modules})
    (info / "top_level.txt").write_text("\n".join(tops) + "\n")
    records = []
    for module in modules:
        path = site_packages / module
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n")
        records.append(f"{module},,")
    records += [f"{info.name}/{f},," for f in ("METADATA", "INSTALLER", "top_level.txt", "RECORD")]
    (info / "RECORD").write_text("\n".join(records) + "\n")


@pytest.fixture
def env(tmp_path):
    target = tmp_path / "venv"
    venv.EnvBuilder(with_pip=True).create(target)
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    sp = Path(subprocess.check_output([str(python), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                                      text=True).strip())
    helper = tmp_path / "helper.py"
    helper.write_text(helper_from(ROOT / "install.sh"))
    run = lambda mode: subprocess.run([str(python), str(helper), mode], capture_output=True, text=True, timeout=120)
    return sp, run


def test_two_providers_fail_the_check_and_clean_removes_them(env):
    sp, run = env
    fake_dist(sp, "pwm-ai4science", "0.6.34.dev0", ["ai4science/__init__.py", "ai4science/legacy.py"])
    fake_dist(sp, "pwm-agent-core", "1.0.1", ["ai4science/__init__.py", "ai4science/core.py"])
    fake_dist(sp, "unrelated-dist", "1.0", ["unrelated/__init__.py"])
    (sp / "~wm_ai4science-0.6.33.dist-info").mkdir()
    (sp / "~i4science").mkdir()

    before = run("check")
    assert before.returncode == 1 and "pwm-agent-core 1.0.1" in before.stdout and "pwm-ai4science 0.6.34.dev0" in before.stdout

    cleaned = run("clean")
    assert cleaned.returncode == 0, cleaned.stdout + cleaned.stderr
    assert not [p.name for p in sp.iterdir() if p.name.startswith("~")]
    names = {p.name for p in sp.iterdir()}
    assert "pwm_ai4science-0.6.34.dev0.dist-info" not in names
    assert "pwm_agent_core-1.0.1.dist-info" not in names      # removed too: the legacy uninstall broke it
    assert "unrelated_dist-1.0.dist-info" in names and (sp / "unrelated/__init__.py").exists()
    assert run("check").returncode == 1                      # nothing provides ai4science yet

    fake_dist(sp, "pwm-agent-core", "1.0.2", ["ai4science/__init__.py", "ai4science/core.py"])   # the install step
    after = run("check")
    assert after.returncode == 0 and "pwm-agent-core 1.0.2" in after.stdout


def test_clean_keeps_a_lone_current_core(env):
    sp, run = env
    fake_dist(sp, "pwm-agent-core", "1.0.1", ["ai4science/__init__.py"])
    assert run("clean").returncode == 0
    assert (sp / "pwm_agent_core-1.0.1.dist-info").is_dir()
    assert run("check").returncode == 0


def test_a_meta_package_without_files_is_not_a_provider(env):
    sp, run = env
    fake_dist(sp, "pwm-agent-core", "1.0.1", ["ai4science/__init__.py"])
    fake_dist(sp, "pwm-ai4science", "1.0.0", [])   # the 1.x PyPI meta-package ships no ai4science/ files
    assert run("check").returncode == 0
    assert run("clean").returncode == 0 and (sp / "pwm_ai4science-1.0.0.dist-info").is_dir()


PWSH = __import__("shutil").which("pwsh") or __import__("shutil").which("powershell")


@pytest.mark.skipif(not PWSH, reason="PowerShell is not installed")
def test_powershell_runs_the_helper_from_its_here_string(env, tmp_path):
    """install.ps1's own Invoke-VenvHelper (here-string -> file -> venv Python -> exit code), run by PowerShell."""
    sp, _run = env
    fake_dist(sp, "pwm-ai4science", "0.6.34.dev0", ["ai4science/__init__.py"])
    fake_dist(sp, "pwm-agent-core", "1.0.1", ["ai4science/__init__.py"])
    source = (ROOT / "install.ps1").read_text(encoding="ascii")
    block = source.split("# -- one provider of the ai4science package", 1)[1].split("# -- venv + install ", 1)[0]
    block = block[block.index("\n"):]
    python = next(p for p in (sp.parents[2] / "bin" / "python", sp.parents[1] / "Scripts" / "python.exe") if p.exists())
    result = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-Command", f"""
$ErrorActionPreference = 'Stop'
$InstallDir = '{tmp_path}'; $venvPython = '{python}'
{block}
$a = Invoke-VenvHelper 'check'; $b = Invoke-VenvHelper 'clean'; $c = Invoke-VenvHelper 'check'
Write-Output "codes $a $b $c"
"""], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "codes 1 0 1" in result.stdout, result.stdout     # two providers -> clean -> none left yet
    assert not (tmp_path / ".venv-helper.py").exists()

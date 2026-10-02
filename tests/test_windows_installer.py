"""Windows installer guards plus isolated PowerShell logic tests (no downloads)."""
from pathlib import Path
import json
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PS1_FILES = sorted(ROOT.rglob("*.ps1"))
PWSH = shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.parametrize("path", PS1_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_powershell_files_are_ascii(path):
    data = path.read_bytes()
    bad = [(i, byte) for i, byte in enumerate(data) if byte > 127]
    assert not bad, f"{path.relative_to(ROOT)} has non-ASCII bytes: {bad[:10]}"


def test_installer_copies_match():
    assert (ROOT / "install.ps1").read_bytes() == (ROOT / "scripts/install.ps1").read_bytes()


def run_powershell(code):
    result = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", code],
        text=True, capture_output=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout.splitlines()[-1])


@pytest.mark.skipif(not PWSH, reason="PowerShell is not installed")
@pytest.mark.parametrize("path", PS1_FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_powershell_parses(path):
    escaped = str(path).replace("'", "''")
    result = run_powershell(f"""
$tokens = $null; $errors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile('{escaped}', [ref]$tokens, [ref]$errors)
ConvertTo-Json -Compress -InputObject @($errors | ForEach-Object {{ $_.Message }})
""")
    assert result == []


@pytest.mark.skipif(not PWSH, reason="PowerShell is not installed")
@pytest.mark.parametrize("reuse,locked,pip_exit,venv_exit", [
    (False, False, 0, 0), (True, False, 0, 0),
    (True, True, 0, 0), (True, False, 1, 0), (False, False, 0, 1),
])
def test_venv_upgrade_logic(reuse, locked, pip_exit, venv_exit):
    source = (ROOT / "install.ps1").read_text(encoding="ascii")
    block = source.split('# -- venv + install ', 1)[1].split('# -- PATH ', 1)[0]
    block = block[block.index('\n'):]
    result = run_powershell(f"""
$ErrorActionPreference = 'Stop'
$Venv = 'test-venv'; $venvPython = 'Test-Python'; $py = 'Test-Python'
$ReuseVenv = ${str(reuse).lower()}; $Channel = 'dev'; $Branch = 'main'
$Version = ''; $IsLegacyTag = $false; $AgentPkgs = @('agent-one', 'agent-two')
$global:calls = [System.Collections.Generic.List[string]]::new()
function Say($m) {{}}
function Ok($m) {{}}
function Test-Path($Path) {{ return $true }}
function Get-SrcSpec {{ return 'test-core @ test.zip' }}
function Test-Python {{
    [void]$global:calls.Add(($args -join ' '))
    if ($args[1] -eq 'venv') {{ $global:LASTEXITCODE = {venv_exit} }}
    else {{ $global:LASTEXITCODE = {pip_exit} }}
}}
function Get-Process {{
    if (${str(locked).lower()}) {{
        [pscustomobject]@{{Path = (Join-Path $Venv 'Scripts') + '\\python.exe'; ProcessName = 'python'; Id = 123}}
    }}
}}
$message = ''
try {{
{block}
}} catch {{ $message = $_.Exception.Message }}
ConvertTo-Json -Compress -InputObject @{{ calls = @($global:calls.ToArray()); message = $message }}
""")
    calls, message = result["calls"], result["message"]
    creation = [c for c in calls if c.startswith("-m venv ")]
    assert len(creation) == (0 if reuse else 1)
    if locked:
        assert "Close" in message and "python (PID 123)" in message
        assert calls == []
    elif venv_exit:
        assert "Could not create venv" in message
        assert len(calls) == 1
    elif pip_exit:
        assert "exit 1" in message and "close ai4science" in message
        assert len(calls) == 1  # stop immediately; no later package installs
    else:
        assert message == ""
        assert sum(c.startswith('-m pip install --upgrade ') for c in calls) == 3


@pytest.mark.skipif(not PWSH, reason="PowerShell is not installed")
@pytest.mark.parametrize("complete,supported", [(False, True), (True, False), (True, True)])
def test_existing_venv_checked_before_python_discovery(complete, supported):
    source = (ROOT / "install.ps1").read_text(encoding="ascii")
    block = source.split('$py = $null\n', 1)[1].split('foreach ($c in', 1)[0]
    result = run_powershell(f"""
$ErrorActionPreference = 'Stop'
$ReuseVenv = $true; $Venv = 'test-venv'; $InstallDir = 'test-home'
$venvPython = 'Test-Python'; $py = $null
function Test-Path($Path) {{ return ${str(complete).lower()} }}
function Test-Python {{ $global:LASTEXITCODE = 0; return '{int(supported)}' }}
$message = ''
try {{
{block}
}} catch {{ $message = $_.Exception.Message }}
ConvertTo-Json -Compress -InputObject @{{python = $py; message = $message}}
""")
    if complete and supported:
        assert result == {"python": "Test-Python", "message": ""}
    else:
        assert result["python"] is None
        assert "Close ai4science" in result["message"]
        assert "ONLY" in result["message"]

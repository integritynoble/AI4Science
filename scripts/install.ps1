# AI4Science installer for Windows — the Claude Code pattern:
#
#   irm https://physicsworldmodel.org/install.ps1 | iex
#
# Installs the `ai4science` CLI (pwm-ai4science[claude]) from GitHub.
# No git required (installs from the GitHub zip archive). Safe to re-run.
$ErrorActionPreference = "Stop"

# The repo zip builds the RUNTIME dist `pwm-agent-core` (since 1.0); the 8
# first-party agents are separate PyPI packages installed right after.
$Spec = "pwm-agent-core[claude] @ https://github.com/integritynoble/AI4Science/archive/refs/heads/main.zip"
$AgentPkgs = "pwm-agent-research pwm-agent-paper pwm-agent-imaging pwm-agent-drug pwm-agent-cancer pwm-agent-unified pwm-agent-claude-gpu pwm-agent-codex-gpu"

function Find-Python {
    foreach ($c in @("py -3", "python", "python3")) {
        try {
            $v = Invoke-Expression "$c -c `"import sys; print('.'.join(map(str, sys.version_info[:2])))`"" 2>$null
            if ($v -and [version]$v -ge [version]"3.10") { return $c }
        } catch {}
    }
    return $null
}

$Py = Find-Python
if (-not $Py) {
    Write-Host "python >= 3.10 is required. Install it from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "(check 'Add python.exe to PATH' in the installer), then re-run." -ForegroundColor Red
    exit 1
}

Write-Host "- installing AI4Science (pwm-agent-core[claude] + agents) ..." -ForegroundColor Cyan
Invoke-Expression "$Py -m pip install --user --upgrade --no-cache-dir `"$Spec`""
Invoke-Expression "$Py -m pip install --user --no-cache-dir $AgentPkgs"

# Add the user scripts dir to PATH automatically (like Claude Code's installer)
$UserScripts = Invoke-Expression "$Py -c `"import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))`""
if ($env:Path -notlike "*$UserScripts*") {
    $up = [Environment]::GetEnvironmentVariable("Path", "User")
    if (-not $up) { $up = "" }
    if ($up -notlike "*$UserScripts*") {
        [Environment]::SetEnvironmentVariable("Path", ($up.TrimEnd(';') + ";" + $UserScripts), "User")
        Write-Host "- added to your user PATH: $UserScripts" -ForegroundColor Cyan
    }
    $env:Path = $env:Path.TrimEnd(';') + ";" + $UserScripts   # current session too
}

Write-Host ""
Write-Host "+ AI4Science installed." -ForegroundColor Green
Write-Host ""
Write-Host "Next steps (like Claude Code):"
Write-Host "  1.  ai4science login        # browser approval on physicsworldmodel.org"
Write-Host "  2.  ai4science              # start chatting; /mode picks an agent"
Write-Host ""
Write-Host "If your network blocks physicsworldmodel.org (some institutions do):"
Write-Host "  ai4science login --base <mirror-url>     # or set PWM_BASE"
Write-Host "Docs: https://physicsworldmodel.org/manual (mirror: GitHub AI4Science/docs)"

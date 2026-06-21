# AI4Science installer for Windows PowerShell — one-line install, no admin.
#
#   irm https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.ps1 | iex
#
# Creates an isolated venv under %USERPROFILE%\.ai4science and adds its
# Scripts dir to your user PATH so `ai4science` is available everywhere.
#
# Env overrides:
#   $env:AI4SCIENCE_HOME         install location (default ~\.ai4science)
#   $env:AI4SCIENCE_WITH_CLAUDE  "0" to skip the [claude] chat-agent extra.
#                                Default installs it so `ai4science` is a
#                                Claude-Code-like chat session.

$ErrorActionPreference = "Stop"

$Pkg = "pwm-ai4science"
$GitUrl = "git+https://github.com/integritynoble/AI4Science.git"
$InstallDir = if ($env:AI4SCIENCE_HOME) { $env:AI4SCIENCE_HOME } else { Join-Path $HOME ".ai4science" }
$Venv = Join-Path $InstallDir "venv"
$WithClaude = $env:AI4SCIENCE_WITH_CLAUDE -ne "0"
# Pin an exact release with $env:AI4SCIENCE_VERSION (flags can't be passed through
# `irm | iex`). Example:  $env:AI4SCIENCE_VERSION="0.6.21"; irm …/install.ps1 | iex
$Version = if ($env:AI4SCIENCE_VERSION) { ($env:AI4SCIENCE_VERSION -replace '^v','') } else { "" }

function Say($m) { Write-Host "▸ $m" -ForegroundColor Cyan }
function Ok($m)  { Write-Host "✓ $m" -ForegroundColor Green }

# Download a self-contained Python (no admin, no system Python, no compiler) from
# Astral's python-build-standalone into $InstallDir\python and return python.exe.
# This is what makes the installer work on a bare Windows box.
function Get-StandalonePython {
    $pyver  = if ($env:AI4SCIENCE_PYVER) { $env:AI4SCIENCE_PYVER } else { "3.12" }
    $triple = "x86_64-pc-windows-msvc"   # also runs on ARM64 Windows via emulation
    $api    = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    # Windows PowerShell 5.1 (the OS default) defaults to TLS 1.0/1.1; GitHub
    # requires TLS 1.2, so opt in explicitly before any web request.
    try { [Net.ServicePointManager]::SecurityProtocol =
          [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch {}
    try {
        $rel = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "ai4science-install" }
    } catch { return $null }
    $asset = $rel.assets |
        Where-Object { $_.name -like "cpython-$pyver.*-$triple-install_only.tar.gz" } |
        Select-Object -First 1
    if (-not $asset) { return $null }
    Say "No suitable Python found — downloading a standalone Python $pyver…"
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $tgz   = Join-Path $InstallDir ".python-dl.tar.gz"
    $pydir = Join-Path $InstallDir "python"
    $oldPP = $ProgressPreference; $ProgressPreference = "SilentlyContinue"
    try {
        Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $tgz -UseBasicParsing
    } catch { $ProgressPreference = $oldPP; return $null }
    $ProgressPreference = $oldPP
    if (Test-Path $pydir) { Remove-Item -Recurse -Force $pydir }
    # Windows 10 1803+ ships bsdtar as tar.exe; the archive extracts a 'python\' dir.
    & tar -xzf $tgz -C $InstallDir
    Remove-Item -Force $tgz -ErrorAction SilentlyContinue
    $exe = Join-Path $pydir "python.exe"
    if (Test-Path $exe) { return $exe } else { return $null }
}

Say "Installing AI4Science (command: ai4science)…"

# 1. Find Python 3.10+ — or download a self-contained one if none is suitable.
$py = $null
foreach ($c in @("python", "python3", "py")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
        $okver = & $c -c "import sys; print(1 if sys.version_info[:2] >= (3,10) else 0)" 2>$null
        if ($okver -eq "1") { $py = $c; break }
    }
}
if (-not $py) {
    $py = Get-StandalonePython
}
if (-not $py) {
    throw "Python 3.10+ not found and auto-download failed (no network?). Install it:  winget install Python.Python.3.12   (or https://www.python.org/downloads/windows/)"
}
Ok "Using $(& $py --version)"

# 2. venv.
Say "Creating venv at $Venv"
& $py -m venv $Venv
$pip = Join-Path $Venv "Scripts\pip.exe"
& $pip install --quiet --upgrade pip | Out-Null

# 3. Install — pinned version (tag zip) first, else PyPI, else GitHub.
$extra = if ($WithClaude) { "[claude]" } else { "" }
$installed = $false
if ($Version) {
    $tag = "https://github.com/integritynoble/AI4Science/archive/refs/tags/v$Version.zip"
    Say "Installing pinned version v$Version…"
    $src = if ($extra) { "$Pkg$extra @ $tag" } else { $tag }
    & $pip install --quiet $src
    if ($LASTEXITCODE -eq 0) { $installed = $true; Ok "Installed $Pkg v$Version from GitHub" }
    else { throw "Could not install v$Version (does that tag exist? e.g. v0.6.21, v0.6.20)" }
}
if (-not $installed) {
    try {
        & $pip install --quiet "$Pkg$extra"
        if ($LASTEXITCODE -eq 0) { $installed = $true; Ok "Installed $Pkg from PyPI" }
    } catch { }
}
if (-not $installed) {
    Say "PyPI unavailable; installing from GitHub…"
    # PEP 508 direct reference for extras (the old '#egg=name[extra]' fragment is
    # rejected by modern pip as an invalid egg fragment).
    $src = if ($extra) { "$Pkg$extra @ $GitUrl" } else { $GitUrl }
    & $pip install --quiet $src
    Ok "Installed $Pkg from GitHub"
}

# 4. Add the venv Scripts dir to the user PATH.
$scripts = Join-Path $Venv "Scripts"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$scripts;$userPath", "User")
    Ok "Added $scripts to your user PATH (restart the terminal to pick it up)"
}

$exe = Join-Path $scripts "ai4science.exe"
Ok "Installed: $(& $exe version)"

Write-Host "`nDone. Open a new terminal, then:"
if ($WithClaude) {
    Ok "Chat agent (Claude Code-like) installed."
    Write-Host "  Start a chat session:  ai4science"
    if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
        Write-Host "`n  The chat agent also needs the claude CLI:" -ForegroundColor Yellow
        Write-Host "    npm install -g @anthropic-ai/claude-code   # then: claude login"
        Write-Host "    (or set `$env:ANTHROPIC_API_KEY). Until then the commands below work offline.)"
    }
    Write-Host "`n  Or a deterministic command:  ai4science init my-first-contribution"
    Write-Host "  Lean install without the chat agent:  `$env:AI4SCIENCE_WITH_CLAUDE='0'; irm … | iex"
} else {
    Write-Host "  ai4science --help"
    Write-Host "  ai4science init my-first-contribution"
    Write-Host "`n  Chat agent skipped (AI4SCIENCE_WITH_CLAUDE=0). Reinstall with the default"
    Write-Host "  to enable it, plus:  npm install -g @anthropic-ai/claude-code; claude login"
}

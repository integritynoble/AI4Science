# AI4Science installer for Windows PowerShell — one-line install, no admin, no Python required.
#
#   irm https://physicsworldmodel.org/install.ps1 | iex
#
# Strategy (tried in order, first success wins):
#   1. Existing Python 3.10+ on PATH
#   2. uv  (Astral single-binary tool manager — installs Python automatically, no admin)
#   3. Standalone Python from Astral's python-build-standalone
#   4. Python embeddable zip from python.org + get-pip.py
#
# Creates an isolated install under %USERPROFILE%\.ai4science and adds its
# Scripts dir to your user PATH so `ai4science` is available everywhere.
#
# Env overrides:
#   $env:AI4SCIENCE_HOME         install location (default ~\.ai4science)
#   $env:AI4SCIENCE_WITH_CLAUDE  "0" to skip the [claude] chat-agent extra.
#   $env:AI4SCIENCE_VERSION      pin a specific release (e.g. "0.6.21")
#   $env:AI4SCIENCE_PYVER        standalone Python version to download (default "3.12")
#   $env:AI4SCIENCE_CHANNEL      stable (default) | rc | dev — picks the GitHub
#                                branch zip (stable.zip / rc.zip / main.zip)

$ErrorActionPreference = "Stop"

$Pkg       = "pwm-ai4science"
$InstallDir = if ($env:AI4SCIENCE_HOME) { $env:AI4SCIENCE_HOME } else { Join-Path $HOME ".ai4science" }
$Venv      = Join-Path $InstallDir "venv"
$WithClaude = $env:AI4SCIENCE_WITH_CLAUDE -ne "0"
$Version   = if ($env:AI4SCIENCE_VERSION) { ($env:AI4SCIENCE_VERSION -replace '^v','') } else { "" }
$PyVer     = if ($env:AI4SCIENCE_PYVER) { $env:AI4SCIENCE_PYVER } else { "3.12" }

# Release channel → GitHub branch zip (no git needed). Default stable, matching
# install.sh. PyPI is not published yet (phase 2), so we install from the branch
# zip directly — uv and pip both get this URL, never a bare PyPI name (which 404s).
$Channel   = if ($env:AI4SCIENCE_CHANNEL) { $env:AI4SCIENCE_CHANNEL.ToLower() } else { "stable" }
$Branch    = switch ($Channel) { "rc" { "rc" } "dev" { "main" } default { "stable" } }
$GitUrl    = "https://github.com/integritynoble/AI4Science/archive/refs/heads/$Branch.zip"
# Source spec with optional [claude] extra, as a PEP 508 direct reference.
# Packaging since 1.0: repo zips build the RUNTIME dist `pwm-agent-core`; the
# 8 first-party agents are separate PyPI packages ($AgentPkgs, installed after
# a zip install). Tags v0.x predate the split and still build the
# self-contained `pwm-ai4science` dist (agents builtin — no top-up, and adding
# core 1.x next to it would shadow the old runtime).
$Extra     = if ($WithClaude) { "[claude]" } else { "" }
$AgentPkgs = @("pwm-agent-research","pwm-agent-paper","pwm-agent-imaging","pwm-agent-drug",
               "pwm-agent-cancer","pwm-agent-unified","pwm-agent-claude-gpu","pwm-agent-codex-gpu")
$IsLegacyTag = [bool]($Version -and $Version -like "0.*")
function Get-SrcSpec {
    if ($Version) {
        $tag = "https://github.com/integritynoble/AI4Science/archive/refs/tags/v$Version.zip"
        if ($IsLegacyTag) { return "pwm-ai4science$Extra @ $tag" }
        return "pwm-agent-core$Extra @ $tag"
    }
    return "pwm-agent-core$Extra @ $GitUrl"
}

function Say($m) { Write-Host "▸ $m" -ForegroundColor Cyan }
function Ok($m)  { Write-Host "✓ $m" -ForegroundColor Green }
function Warn($m){ Write-Host "⚠ $m" -ForegroundColor Yellow }

# Ensure TLS 1.2 for all subsequent web requests (Windows PowerShell 5.1 default is TLS 1.0/1.1)
try {
    [Net.ServicePointManager]::SecurityProtocol =
        [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# ── helper: safe web download ─────────────────────────────────────────────────
function Download-File($uri, $dest) {
    $old = $ProgressPreference; $ProgressPreference = "SilentlyContinue"
    try { Invoke-WebRequest -Uri $uri -OutFile $dest -UseBasicParsing }
    finally { $ProgressPreference = $old }
}

# ── Path 1: existing Python ───────────────────────────────────────────────────
$py = $null
foreach ($c in @("python", "python3", "py")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) {
        try {
            # Redirect both stdout and stderr; catch NativeCommandError from Store alias
            $okver = & $c -c "import sys; print(1 if sys.version_info[:2] >= (3,10) else 0)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $okver -eq "1") { $py = $c; break }
        } catch { }
    }
}

# ── Path 2: uv (recommended — installs its own Python, no admin) ──────────────
$uvExe = $null
if (-not $py) {
    $uvDir = Join-Path $InstallDir "uv"
    $uvBin = Join-Path $uvDir "uv.exe"
    if (-not (Test-Path $uvBin)) {
        Say "Downloading uv (fast Python tool manager, no admin needed)…"
        $uvZip = Join-Path $InstallDir ".uv.zip"
        try {
            Download-File "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" $uvZip
            if (Test-Path $uvDir) { Remove-Item -Recurse -Force $uvDir }
            Expand-Archive -Path $uvZip -DestinationPath $uvDir -Force
            Remove-Item -Force $uvZip -ErrorAction SilentlyContinue
            # The zip may contain a subdirectory; find uv.exe wherever it landed
            $found = Get-ChildItem -Recurse -Filter "uv.exe" $uvDir | Select-Object -First 1
            if ($found) { $uvBin = $found.FullName }
        } catch { Warn "uv download failed — trying standalone Python next." }
    }
    if (Test-Path $uvBin) { $uvExe = $uvBin }
}

if ($uvExe) {
    Say "Installing via uv from the [$Channel] channel…"
    # Install from the GitHub branch zip — NOT a bare PyPI name (pwm-ai4science
    # is not on PyPI yet → 404). uv resolves the [claude] extra from the zip.
    $src = Get-SrcSpec
    # A repo zip is core-only — bring the agent packages into the tool env too.
    $withFlags = @()
    if (-not $IsLegacyTag) { foreach ($p in $AgentPkgs) { $withFlags += @("--with", $p) } }
    try {
        & $uvExe tool install $src @withFlags --force 2>&1
        if ($LASTEXITCODE -eq 0) {
            New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
            Set-Content -Path (Join-Path $InstallDir "channel") -Value $Channel
            $uvToolBin = Join-Path $HOME ".local\bin"
            $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if ($userPath -notlike "*$uvToolBin*") {
                [Environment]::SetEnvironmentVariable("Path", "$uvToolBin;$userPath", "User")
                Ok "Added $uvToolBin to your user PATH (restart terminal to pick it up)"
            }
            Ok "Installed via uv ([$Channel] channel)."
            Write-Host "`nDone. Open a new terminal and run:  ai4science"
            exit 0
        }
    } catch { Warn "uv install failed — falling back to standalone Python." }
}

# ── Path 3: standalone Python from Astral ────────────────────────────────────
if (-not $py) {
    $triple = "x86_64-pc-windows-msvc"
    $api    = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest"
    try {
        $rel   = Invoke-RestMethod -Uri $api -Headers @{ "User-Agent" = "ai4science-install" }
        $asset = $rel.assets |
            Where-Object { $_.name -like "cpython-$PyVer.*-$triple-install_only.tar.gz" } |
            Select-Object -First 1
        if ($asset) {
            Say "Downloading standalone Python $PyVer (no admin, no Store)…"
            $tgz   = Join-Path $InstallDir ".python-dl.tar.gz"
            $pydir = Join-Path $InstallDir "python"
            Download-File $asset.browser_download_url $tgz
            if (Test-Path $pydir) { Remove-Item -Recurse -Force $pydir }
            & tar -xzf $tgz -C $InstallDir
            Remove-Item -Force $tgz -ErrorAction SilentlyContinue
            $exe = Join-Path $pydir "python.exe"
            if (Test-Path $exe) { $py = $exe }
        }
    } catch { Warn "Standalone Python download failed — trying embeddable zip." }
}

# ── Path 4: Python embeddable zip from python.org ────────────────────────────
if (-not $py) {
    # Use a known stable embeddable URL (3.12.7 — update patch as needed)
    $embedVer = "3.12.7"
    $embedUrl = "https://www.python.org/ftp/python/$embedVer/python-$embedVer-embed-amd64.zip"
    $embedDir = Join-Path $InstallDir "python-embed"
    $embedZip = Join-Path $InstallDir ".python-embed.zip"
    Say "Downloading Python $embedVer embeddable (python.org)…"
    try {
        Download-File $embedUrl $embedZip
        if (Test-Path $embedDir) { Remove-Item -Recurse -Force $embedDir }
        Expand-Archive -Path $embedZip -DestinationPath $embedDir -Force
        Remove-Item -Force $embedZip -ErrorAction SilentlyContinue
        $embedPy = Join-Path $embedDir "python.exe"
        # Enable site-packages in the embeddable layout
        $pth = Get-ChildItem $embedDir -Filter "python*._pth" | Select-Object -First 1
        if ($pth) {
            $content = Get-Content $pth.FullName -Raw
            Set-Content $pth.FullName ($content -replace "#import site","import site")
        }
        # Bootstrap pip into the embeddable Python
        $getPip = Join-Path $InstallDir ".get-pip.py"
        Download-File "https://bootstrap.pypa.io/get-pip.py" $getPip
        & $embedPy $getPip --quiet
        Remove-Item -Force $getPip -ErrorAction SilentlyContinue
        if (Test-Path $embedPy) { $py = $embedPy }
    } catch { Warn "Embeddable Python download failed." }
}

if (-not $py) {
    throw @"
Could not find or install Python automatically.
Options:
  • winget install Python.Python.3.12
  • https://www.python.org/downloads/windows/
  • Microsoft Store (search 'Python 3.12') — then re-run this installer
  • Set `$env:AI4SCIENCE_PYVER='3.11' and retry (different version)
"@
}

Ok "Using $(& $py --version 2>&1)"

# ── venv + install ────────────────────────────────────────────────────────────
Say "Creating venv at $Venv"
& $py -m venv $Venv
$pip     = Join-Path $Venv "Scripts\pip.exe"
$scripts = Join-Path $Venv "Scripts"
& $pip install --quiet --upgrade pip | Out-Null

# Install from the channel's GitHub branch zip (PyPI is not published yet).
$src = Get-SrcSpec
if ($Version) { Say "Installing pinned version v$Version…" }
else { Say "Installing the [$Channel] channel from GitHub ($Branch.zip)…" }
& $pip install --quiet $src
if ($LASTEXITCODE -eq 0) {
    Set-Content -Path (Join-Path $InstallDir "channel") -Value $Channel
    Ok "Installed ([$Channel] channel)"
} else {
    throw "Install failed from $GitUrl — check your network connection."
}

# A repo zip is core-only — install the first-party agent packages from PyPI.
if (-not $IsLegacyTag) {
    Say "Installing the first-party agent packages…"
    & $pip install --quiet @AgentPkgs
    if ($LASTEXITCODE -eq 0) { Ok "Installed agent packages" }
    else { Warn "agent packages failed to install — run: $pip install $($AgentPkgs -join ' ')" }
}

# ── PATH ──────────────────────────────────────────────────────────────────────
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$scripts*") {
    [Environment]::SetEnvironmentVariable("Path", "$scripts;$userPath", "User")
    Ok "Added $scripts to your user PATH (restart terminal to pick it up)"
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
    }
    Write-Host "`n  Or a deterministic command:  ai4science init my-first-contribution"
} else {
    Write-Host "  ai4science --help"
    Write-Host "  ai4science init my-first-contribution"
}

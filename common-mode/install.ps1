param([string]$Prefix = $(Join-Path $env:LOCALAPPDATA 'AI4Science/Common'))
$ErrorActionPreference = 'Stop'
$ai4scienceSource = $PSScriptRoot
$Prefix = [IO.Path]::GetFullPath($Prefix)
if (Test-Path -LiteralPath $Prefix) { throw 'Prefix already exists; choose an empty installation prefix.' }
$ai4scienceArch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
$ai4sciencePackage = switch ($ai4scienceArch) {
    'AMD64' { 'opencode-windows-x64-baseline' }
    'ARM64' { 'opencode-windows-arm64' }
    default { throw 'Supported Windows CPUs: x64 and arm64.' }
}
$ai4scienceRecord = Get-Content -LiteralPath (Join-Path $ai4scienceSource 'artifacts.lock') | Where-Object { $_.StartsWith("$ai4sciencePackage ") } | Select-Object -First 1
if (!$ai4scienceRecord) { throw 'No pinned artifact for this platform.' }
$ai4scienceParts = $ai4scienceRecord.Split(' ')
$ai4scienceStage = Join-Path ([IO.Path]::GetTempPath()) ('ai4science-install-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $ai4scienceStage | Out-Null
$ai4scienceArchive = Join-Path $ai4scienceStage 'engine.tgz'
try {
    if ($env:AI4SCIENCE_ARTIFACT) {
        Copy-Item -LiteralPath $env:AI4SCIENCE_ARTIFACT -Destination $ai4scienceArchive
    } else {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri $ai4scienceParts[2] -OutFile $ai4scienceArchive
    }
    $ai4scienceHash = (Get-FileHash -Algorithm SHA512 -LiteralPath $ai4scienceArchive).Hash.ToLowerInvariant()
    if ($ai4scienceHash -ne $ai4scienceParts[1]) { throw 'Pinned artifact checksum mismatch; nothing installed.' }
    # tar.exe ships with current Windows 10/11; no git, Node, or npm required.
    & tar.exe -xzf $ai4scienceArchive -C $ai4scienceStage
    if ($LASTEXITCODE -ne 0) { throw 'Archive extraction failed. Windows tar.exe is required.' }
    $ai4scienceRgArch = if ($ai4scienceArch -eq 'ARM64') { 'windows-arm64' } else { 'windows-x64' }
    $ai4scienceRgRecord = Get-Content -LiteralPath (Join-Path $ai4scienceSource 'ripgrep.lock') | Where-Object { $_.StartsWith("$ai4scienceRgArch ") } | Select-Object -First 1
    if (!$ai4scienceRgRecord) { throw 'No pinned ripgrep for this platform.' }
    $ai4scienceRgParts = $ai4scienceRgRecord.Split(' ')
    $ai4scienceRgArchive = Join-Path $ai4scienceStage 'ripgrep.zip'
    if ($env:AI4SCIENCE_RIPGREP_ARTIFACT) {
        Copy-Item -LiteralPath $env:AI4SCIENCE_RIPGREP_ARTIFACT -Destination $ai4scienceRgArchive
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $ai4scienceRgParts[2] -OutFile $ai4scienceRgArchive
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $ai4scienceRgArchive).Hash.ToLowerInvariant() -ne $ai4scienceRgParts[1]) { throw 'Pinned ripgrep checksum mismatch; nothing installed.' }
    Expand-Archive -LiteralPath $ai4scienceRgArchive -DestinationPath $ai4scienceStage
    $ai4scienceRgDir = Join-Path $ai4scienceStage ([IO.Path]::GetFileNameWithoutExtension($ai4scienceRgParts[2]))
    $ai4scienceConfig = Join-Path $Prefix 'var/config/opencode'
    $ai4scienceBin = Join-Path $Prefix 'bin'
    $ai4scienceShare = Join-Path $Prefix 'share'
    foreach ($ai4scienceDir in @($ai4scienceBin, $ai4scienceConfig, $ai4scienceShare)) {
        New-Item -ItemType Directory -Path $ai4scienceDir -Force | Out-Null
    }
    $ai4scienceRgBin = Join-Path $Prefix 'var/cache/opencode/bin'
    $ai4scienceRgNotices = Join-Path $ai4scienceShare 'ripgrep'
    New-Item -ItemType Directory -Path $ai4scienceRgBin, $ai4scienceRgNotices -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $ai4scienceRgDir 'rg.exe') -Destination $ai4scienceRgBin
    foreach ($ai4scienceFile in @('COPYING', 'LICENSE-MIT', 'UNLICENSE')) {
        Copy-Item -LiteralPath (Join-Path $ai4scienceRgDir $ai4scienceFile) -Destination $ai4scienceRgNotices
    }
    Copy-Item -LiteralPath (Join-Path $ai4scienceStage 'package/bin/opencode.exe') -Destination $ai4scienceBin
    foreach ($ai4scienceFile in @('ai4science.ps1', 'ai4science.cmd')) {
        Copy-Item -LiteralPath (Join-Path $ai4scienceSource $ai4scienceFile) -Destination $ai4scienceBin
    }
    foreach ($ai4scienceFile in @('THIRD_PARTY_NOTICES.md', 'README.md', 'opencode.version', 'artifacts.lock', 'ripgrep.lock')) {
        Copy-Item -LiteralPath (Join-Path $ai4scienceSource $ai4scienceFile) -Destination $ai4scienceShare
    }
    $ai4scienceUtf8 = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText((Join-Path $Prefix 'empty-user.npmrc'), '', $ai4scienceUtf8)
    [IO.File]::WriteAllText((Join-Path $Prefix 'empty-global.npmrc'), '', $ai4scienceUtf8)
    $ai4scienceDefaults = [IO.File]::ReadAllText((Join-Path $ai4scienceSource 'defaults.json'))
    $ai4sciencePrime = $ai4scienceDefaults.Replace('"plugin": []', '"plugin": ["./install-prime.mjs"]')
    [IO.File]::WriteAllText((Join-Path $ai4scienceConfig 'opencode.json'), $ai4sciencePrime, $ai4scienceUtf8)
    [IO.File]::WriteAllText((Join-Path $ai4scienceConfig 'install-prime.mjs'), 'export default async () => ({})', $ai4scienceUtf8)
    $ai4scienceVersion = & (Join-Path $ai4scienceBin 'opencode.exe') --version
    if ($LASTEXITCODE -ne 0 -or $ai4scienceVersion -ne (Get-Content -Raw (Join-Path $ai4scienceSource 'opencode.version')).Trim()) { throw 'Unexpected engine version.' }
    $ai4scienceOldInstall = $env:AI4SCIENCE_INSTALL_DEPENDENCIES
    try {
        $env:AI4SCIENCE_INSTALL_DEPENDENCIES = '1'
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ai4scienceBin 'ai4science.ps1') models own-llm 1> (Join-Path $Prefix 'var/install-models.txt') 2> (Join-Path $Prefix 'var/install.log')
        if ($LASTEXITCODE -ne 0) { throw 'Dependency setup failed. Private diagnostic log: PREFIX/var/install.log.' }
    } finally {
        $env:AI4SCIENCE_INSTALL_DEPENDENCIES = $ai4scienceOldInstall
        [IO.File]::WriteAllText((Join-Path $ai4scienceConfig 'opencode.json'), $ai4scienceDefaults, $ai4scienceUtf8)
        Remove-Item -LiteralPath (Join-Path $ai4scienceConfig 'install-prime.mjs')
    }
    if (!(Test-Path -LiteralPath (Join-Path $ai4scienceConfig 'node_modules/@opencode-ai/plugin'))) { throw 'Config dependency setup did not finish; see PREFIX/var/install.log.' }
    & (Join-Path $ai4scienceBin 'ai4science.cmd') --version
    if ($LASTEXITCODE -ne 0) { throw 'Installed wrapper failed its version check.' }
    Write-Output "Installed. Add this directory to PATH: $ai4scienceBin"
} finally {
    # Only remove the unique temporary directory created by this installer.
    Remove-Item -LiteralPath $ai4scienceStage -Recurse
}

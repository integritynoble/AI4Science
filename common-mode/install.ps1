$ErrorActionPreference = 'Stop'
$Version = (Get-Content (Join-Path $PSScriptRoot 'VERSION') -Raw).Trim()
$Prefix = if ($env:AI4SCIENCE_PREFIX) { $env:AI4SCIENCE_PREFIX } else { Join-Path $env:LOCALAPPDATA 'AI4Science' }
$Arch = if ([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'x64' }
$Package = "opencode-windows-$Arch"
$Integrity = switch ($Package) {
    'opencode-windows-x64' { 'sha512-jNrfHad+xUpGNL7doZkjfDGvNYuff1IzPT7VqqjzUUeH4ZOIDpzpC1VRsiauSczhrhfj0X59lb72U7DbUGl/dg==' }
    'opencode-windows-arm64' { 'sha512-ZuUMjYBlY8mGuQvCRYTKOluqsh47+XmOZw62e3+Gn2XdSBe+fysxQaZqdhzYHq0kOFm30kEkp8alN7X5rLticg==' }
}
$Archive = Join-Path $env:TEMP "ai4science-opencode-$Version.tgz"
$Unpack = Join-Path $env:TEMP "ai4science-opencode-$Version"
if ($env:AI4SCIENCE_PACKAGE_ARCHIVE) {
    Copy-Item $env:AI4SCIENCE_PACKAGE_ARCHIVE $Archive -Force
} else {
    $Url = "https://registry.npmjs.org/$Package/-/$Package-$Version.tgz"
    Invoke-WebRequest -Uri $Url -OutFile $Archive
}
$HashHex = (Get-FileHash -Algorithm SHA512 -Path $Archive).Hash
$HashBytes = for ($i = 0; $i -lt $HashHex.Length; $i += 2) { [Convert]::ToByte($HashHex.Substring($i, 2), 16) }
$ActualIntegrity = 'sha512-' + [Convert]::ToBase64String([byte[]]$HashBytes)
if ($ActualIntegrity -ne $Integrity) { throw "OpenCode package integrity check failed for $Package@$Version" }
New-Item -ItemType Directory -Force -Path (Join-Path $Prefix 'bin'), (Join-Path $Prefix 'config'), $Unpack | Out-Null
tar -xzf $Archive -C $Unpack
Copy-Item (Join-Path $Unpack 'package/bin/opencode.exe') (Join-Path $Prefix 'bin/opencode.exe') -Force
Copy-Item (Join-Path $PSScriptRoot 'ai4science.ps1') (Join-Path $Prefix 'bin/ai4science.ps1') -Force
if (-not (Test-Path (Join-Path $Prefix 'config/opencode.json'))) {
    Copy-Item (Join-Path $PSScriptRoot 'opencode.json') (Join-Path $Prefix 'config/opencode.json')
}
if (-not (Test-Path (Join-Path $Prefix '.provider-primed'))) {
    $env:AI4SCIENCE_PREFIX = $Prefix
    $env:OPENCODE_CONFIG_DIR = Join-Path $Prefix 'config'
    $env:OPENCODE_CONFIG = Join-Path $Prefix 'config/opencode.json'
    $env:XDG_CONFIG_HOME = Join-Path $Prefix 'xdg/config'
    $env:XDG_DATA_HOME = Join-Path $Prefix 'xdg/data'
    $env:XDG_CACHE_HOME = Join-Path $Prefix 'xdg/cache'
    $env:XDG_STATE_HOME = Join-Path $Prefix 'xdg/state'
    $env:OPENCODE_DISABLE_AUTOUPDATE = '1'
    $env:OPENCODE_DISABLE_MODELS_FETCH = '1'
    $env:OPENCODE_DISABLE_DEFAULT_PLUGINS = '1'
    $env:OPENCODE_DISABLE_LSP_DOWNLOAD = '1'
    $env:AI4SCIENCE_OPENAI_BASE_URL = 'http://127.0.0.1:1/v1'
    $env:OPENAI_API_KEY = 'ai4science-install-placeholder'
    & (Join-Path $Prefix 'bin/opencode.exe') run --format json 'bootstrap local provider' *> $null
    if (-not (Test-Path (Join-Path $Prefix 'xdg/config/opencode/node_modules/@opencode-ai/sdk/package.json'))) {
        throw 'OpenCode provider setup did not complete; check network access to npm and retry.'
    }
    New-Item -ItemType File (Join-Path $Prefix '.provider-primed') -Force | Out-Null
}
Write-Output "Installed AI4Science common mode (OpenCode $Version) in $Prefix"

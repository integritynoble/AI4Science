$ErrorActionPreference = 'Stop'
$ai4sciencePrefix = Split-Path -Parent $PSScriptRoot
$ai4scienceConfig = Join-Path $ai4sciencePrefix 'var/config/opencode'
# Wrapper-owned option (before any engine arguments): the folder a session works in.
$ai4scienceArgs = @($args)
$ai4scienceWorkspace = $env:AI4SCIENCE_WORKSPACE
$ai4sciencePwm = $false
while ($ai4scienceArgs.Count -gt 0) {
    if ($ai4scienceArgs[0] -eq '--pwm') {
        $ai4sciencePwm = $true
        $ai4scienceArgs = @($ai4scienceArgs | Select-Object -Skip 1)
    } elseif ($ai4scienceArgs[0] -eq '--workspace') {
        if ($ai4scienceArgs.Count -lt 2 -or !$ai4scienceArgs[1]) {
            [Console]::Error.WriteLine('Usage: ai4science --workspace DIRECTORY [command] [arguments]')
            exit 2
        }
        $ai4scienceWorkspace = $ai4scienceArgs[1]
        $ai4scienceArgs = @($ai4scienceArgs | Select-Object -Skip 2)
    } else { break }
}
$ai4scienceRemoteAction = $null
if ($ai4scienceArgs.Count -gt 0 -and $ai4scienceArgs[0] -eq 'pwm') {
    if ($ai4scienceArgs.Count -ne 2 -or $ai4scienceArgs[1] -notin @('login', 'logout')) {
        [Console]::Error.WriteLine('Usage: ai4science pwm login|logout')
        exit 2
    }
    $ai4scienceRemoteAction = $ai4scienceArgs[1]
} elseif ($ai4sciencePwm) { $ai4scienceRemoteAction = 'on' }
elseif (Test-Path -LiteralPath (Join-Path $ai4sciencePrefix 'var/pwm/base-config')) { $ai4scienceRemoteAction = 'off' }
if ($ai4scienceRemoteAction) {
    . (Join-Path $PSScriptRoot 'pwm-config.ps1')
    try { Invoke-Ai4ScienceRemote $ai4sciencePrefix $ai4scienceRemoteAction }
    catch {
        [Console]::Error.WriteLine('Unable to prepare private remote configuration; check AI4SCIENCE_PWM_URL (https required), saved login and private storage.')
        exit 2
    }
    if ($ai4scienceRemoteAction -in @('login', 'logout')) { exit 0 }
}
if ($ai4scienceWorkspace) {
    if (!(Test-Path -LiteralPath $ai4scienceWorkspace -PathType Container)) {
        [Console]::Error.WriteLine('AI4Science workspace is not a directory.')
        exit 2
    }
    $ai4scienceWorkspace = (Resolve-Path -LiteralPath $ai4scienceWorkspace).ProviderPath
}
$ai4scienceValues = @{
    PATH = ((Join-Path $ai4sciencePrefix 'var/cache/opencode/bin') + ';' + $env:PATH)
    XDG_CONFIG_HOME = (Join-Path $ai4sciencePrefix 'var/config')
    XDG_DATA_HOME = (Join-Path $ai4sciencePrefix 'var/data')
    XDG_CACHE_HOME = (Join-Path $ai4sciencePrefix 'var/cache')
    XDG_STATE_HOME = (Join-Path $ai4sciencePrefix 'var/state')
    OPENCODE_CONFIG_DIR = $ai4scienceConfig
    OPENCODE_CONFIG = (Join-Path $ai4scienceConfig 'opencode.json')
    OPENCODE_TEST_HOME = (Join-Path $ai4sciencePrefix 'var/home')
    OPENCODE_TEST_MANAGED_CONFIG_DIR = (Join-Path $ai4sciencePrefix 'var/managed')
    OPENCODE_DISABLE_PROJECT_CONFIG = '1'
    OPENCODE_DISABLE_AUTOUPDATE = '1'
    OPENCODE_DISABLE_MODELS_FETCH = '1'
    OPENCODE_DISABLE_DEFAULT_PLUGINS = '1'
    OPENCODE_DISABLE_CLAUDE_CODE = '1'
    OPENCODE_DISABLE_EXTERNAL_SKILLS = '1'
    OPENCODE_DISABLE_LSP_DOWNLOAD = '1'
    OPENCODE_DISABLE_FFF = '1'
    OPENCODE_DISABLE_TERMINAL_TITLE = '1'
    OPENCODE_EXPERIMENTAL = '0'
    OTEL_SDK_DISABLED = 'true'
    npm_config_userconfig = (Join-Path $ai4sciencePrefix 'empty-user.npmrc')
    npm_config_globalconfig = (Join-Path $ai4sciencePrefix 'empty-global.npmrc')
    npm_config_cache = (Join-Path $ai4sciencePrefix 'var/npm-cache')
    npm_config_registry = 'https://registry.npmjs.org'
    npm_config_offline = 'true'
    OTEL_EXPORTER_OTLP_ENDPOINT = $null
    OTEL_EXPORTER_OTLP_HEADERS = $null
    HTTP_PROXY = $null
    HTTPS_PROXY = $null
    ALL_PROXY = $null
}
if ($env:AI4SCIENCE_INSTALL_DEPENDENCIES -eq '1') { $ai4scienceValues.npm_config_offline = 'false' }
# `serve` is password-protected only through our own variable; the engine's tools do not inherit it.
if ($env:AI4SCIENCE_SERVER_PASSWORD) {
    $ai4scienceValues.OPENCODE_SERVER_PASSWORD = $env:AI4SCIENCE_SERVER_PASSWORD
    $ai4scienceValues.OPENCODE_SERVER_USERNAME = if ($env:AI4SCIENCE_SERVER_USERNAME) { $env:AI4SCIENCE_SERVER_USERNAME } else { 'opencode' }
}
$ai4scienceValues.AI4SCIENCE_SERVER_PASSWORD = $null
$ai4scienceValues.AI4SCIENCE_BASE_URL = if ($env:AI4SCIENCE_BASE_URL) { $env:AI4SCIENCE_BASE_URL } else { 'http://127.0.0.1:8000/v1' }
$ai4scienceValues.AI4SCIENCE_API_KEY = if ($env:AI4SCIENCE_API_KEY) { $env:AI4SCIENCE_API_KEY } else { 'local-no-key' }
$ai4scienceValues.AI4SCIENCE_MODEL = if ($env:AI4SCIENCE_MODEL) { $env:AI4SCIENCE_MODEL } else { 'local' }
# Clear every inherited upstream variable, then apply our private values.
# Save them with the other overrides so invoking PowerShell callers are restored.
foreach ($ai4scienceName in [Environment]::GetEnvironmentVariables('Process').Keys) {
    if ($ai4scienceName -like 'OPENCODE_*' -and !$ai4scienceValues.ContainsKey($ai4scienceName)) {
        $ai4scienceValues[$ai4scienceName] = $null
    }
}
# PowerShell passes $null to .NET as "", which PowerShell 7 stores as an empty variable; remove instead.
function Set-Ai4ScienceVariable([string]$Name, $Value) {
    if ($null -eq $Value) { Remove-Item -LiteralPath "Env:$Name" -ErrorAction SilentlyContinue }
    else { [Environment]::SetEnvironmentVariable($Name, [string]$Value, 'Process') }
}
$ai4sciencePrevious = @{}
$ai4scienceExit = 1
$ai4sciencePreviousLocation = Get-Location
try {
    foreach ($ai4scienceName in $ai4scienceValues.Keys) {
        $ai4sciencePrevious[$ai4scienceName] = [Environment]::GetEnvironmentVariable($ai4scienceName, 'Process')
        Set-Ai4ScienceVariable $ai4scienceName $ai4scienceValues[$ai4scienceName]
    }
    foreach ($ai4scienceDir in @($ai4scienceConfig, $ai4scienceValues.OPENCODE_TEST_HOME, $ai4scienceValues.OPENCODE_TEST_MANAGED_CONFIG_DIR)) {
        New-Item -ItemType Directory -Force -Path $ai4scienceDir | Out-Null
    }
    # Where the session works (see the POSIX launcher): --workspace DIR keeps project settings off;
    # AI4SCIENCE_PROJECT_CONFIG=1 trusts the current folder's settings; otherwise the private config folder,
    # the one place the engine's v2 loader reads no project files.
    if ($ai4scienceWorkspace) {
        Set-Location -LiteralPath $ai4scienceWorkspace
        if ($env:AI4SCIENCE_PROJECT_CONFIG -eq '1') { $env:OPENCODE_DISABLE_PROJECT_CONFIG = '0' }
    } elseif ($env:AI4SCIENCE_PROJECT_CONFIG -eq '1') {
        $env:OPENCODE_DISABLE_PROJECT_CONFIG = '0'
    } else {
        Set-Location -LiteralPath $ai4scienceConfig
    }
    $ai4scienceEngine = Join-Path $ai4sciencePrefix 'bin/opencode.exe'
    $ai4scienceUpgrade = $false
    foreach ($ai4scienceArg in $ai4scienceArgs) {
        if ($ai4scienceArg -in @('acp', 'mcp', 'attach', 'run', 'generate', 'debug', 'console', 'auth', 'providers', 'agent', 'uninstall', 'serve', 'web', 'models', 'stats', 'export', 'import', 'github', 'pr', 'session', 'plugin', 'db', 'completion')) { break }
        if ($ai4scienceArg -eq 'upgrade') { $ai4scienceUpgrade = $true; break }
    }
    if ($ai4scienceUpgrade) {
        [Console]::Error.WriteLine('AI4Science uses a pinned engine. Update the reviewed wrapper package to upgrade.')
        $ai4scienceExit = 2
    } elseif ($ai4scienceArgs.Count -gt 0 -and $ai4scienceArgs[0] -in @('--version', '-v')) {
        $ai4scienceVersion = & $ai4scienceEngine --version
        $ai4scienceExit = $LASTEXITCODE
        Write-Output "AI4Science common mode (OpenCode $ai4scienceVersion)"
    } else {
        & $ai4scienceEngine @ai4scienceArgs
        $ai4scienceExit = $LASTEXITCODE
    }
} finally {
    Set-Location -LiteralPath $ai4sciencePreviousLocation.Path
    foreach ($ai4scienceName in $ai4sciencePrevious.Keys) {
        Set-Ai4ScienceVariable $ai4scienceName $ai4sciencePrevious[$ai4scienceName]
    }
}
exit $ai4scienceExit

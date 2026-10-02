$ErrorActionPreference = 'Stop'
$ai4sciencePrefix = Split-Path -Parent $PSScriptRoot
$ai4scienceConfig = Join-Path $ai4sciencePrefix 'var/config/opencode'
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
    OPENCODE_CONFIG_CONTENT = $null
    OPENCODE_DB = $null
    OPENCODE_MODELS_PATH = $null
    OPENCODE_MODELS_URL = $null
    OPENCODE_PERMISSION = $null
    OPENCODE_TUI_CONFIG = $null
    OPENCODE_AUTO_SHARE = $null
    OPENCODE_WORKSPACE_ID = $null
    OPENCODE_CONSOLE_TOKEN = $null
    OTEL_EXPORTER_OTLP_ENDPOINT = $null
    OTEL_EXPORTER_OTLP_HEADERS = $null
    HTTP_PROXY = $null
    HTTPS_PROXY = $null
    ALL_PROXY = $null
}
if ($env:AI4SCIENCE_INSTALL_DEPENDENCIES -eq '1') { $ai4scienceValues.npm_config_offline = 'false' }
$ai4scienceValues.AI4SCIENCE_BASE_URL = if ($env:AI4SCIENCE_BASE_URL) { $env:AI4SCIENCE_BASE_URL } else { 'http://127.0.0.1:8000/v1' }
$ai4scienceValues.AI4SCIENCE_API_KEY = if ($env:AI4SCIENCE_API_KEY) { $env:AI4SCIENCE_API_KEY } else { 'local-no-key' }
$ai4scienceValues.AI4SCIENCE_MODEL = if ($env:AI4SCIENCE_MODEL) { $env:AI4SCIENCE_MODEL } else { 'local' }
$ai4sciencePrevious = @{}
$ai4scienceExit = 1
try {
    foreach ($ai4scienceName in $ai4scienceValues.Keys) {
        $ai4sciencePrevious[$ai4scienceName] = [Environment]::GetEnvironmentVariable($ai4scienceName, 'Process')
        [Environment]::SetEnvironmentVariable($ai4scienceName, $ai4scienceValues[$ai4scienceName], 'Process')
    }
    foreach ($ai4scienceDir in @($ai4scienceConfig, $ai4scienceValues.OPENCODE_TEST_HOME, $ai4scienceValues.OPENCODE_TEST_MANAGED_CONFIG_DIR)) {
        New-Item -ItemType Directory -Force -Path $ai4scienceDir | Out-Null
    }
    $ai4scienceEngine = Join-Path $ai4sciencePrefix 'bin/opencode.exe'
    $ai4scienceUpgrade = $false
    foreach ($ai4scienceArg in $args) {
        if ($ai4scienceArg -in @('acp', 'mcp', 'attach', 'run', 'generate', 'debug', 'console', 'auth', 'providers', 'agent', 'uninstall', 'serve', 'web', 'models', 'stats', 'export', 'import', 'github', 'pr', 'session', 'plugin', 'db', 'completion')) { break }
        if ($ai4scienceArg -eq 'upgrade') { $ai4scienceUpgrade = $true; break }
    }
    if ($ai4scienceUpgrade) {
        [Console]::Error.WriteLine('AI4Science uses a pinned engine. Update the reviewed wrapper package to upgrade.')
        $ai4scienceExit = 2
    } elseif ($args.Count -gt 0 -and $args[0] -in @('--version', '-v')) {
        $ai4scienceVersion = & $ai4scienceEngine --version
        $ai4scienceExit = $LASTEXITCODE
        Write-Output "AI4Science common mode (OpenCode $ai4scienceVersion)"
    } else {
        & $ai4scienceEngine @args
        $ai4scienceExit = $LASTEXITCODE
    }
} finally {
    foreach ($ai4scienceName in $ai4sciencePrevious.Keys) {
        [Environment]::SetEnvironmentVariable($ai4scienceName, $ai4sciencePrevious[$ai4scienceName], 'Process')
    }
}
exit $ai4scienceExit

$ErrorActionPreference = 'Stop'
$Prefix = if ($env:AI4SCIENCE_PREFIX) { $env:AI4SCIENCE_PREFIX } else { Join-Path $env:LOCALAPPDATA 'AI4Science' }
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
if (-not $env:AI4SCIENCE_OPENAI_BASE_URL) { $env:AI4SCIENCE_OPENAI_BASE_URL = 'http://127.0.0.1:8000/v1' }
& (Join-Path $Prefix 'bin/opencode.exe') @args
exit $LASTEXITCODE

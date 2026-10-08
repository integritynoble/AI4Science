# Private storage and configuration for an optional remote MCP server.
function Invoke-Ai4ScienceRemote([string]$Prefix, [string]$Action) {
    $store = Join-Path $Prefix 'var/pwm'
    $config = Join-Path $Prefix 'var/config/opencode/opencode.json'
    $keyFile = Join-Path $store 'key'
    $baseline = Join-Path $store 'base-config'
    $utf8 = New-Object Text.UTF8Encoding($false)
    function Protect-PrivatePath([string]$Path, [bool]$Directory) {
        $item = Get-Item -LiteralPath $Path -Force
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe private configuration path.' }
        if ($env:OS -eq 'Windows_NT') {
            $acl = if ($Directory) { New-Object Security.AccessControl.DirectorySecurity } else { New-Object Security.AccessControl.FileSecurity }
            $acl.SetAccessRuleProtection($true, $false)
            $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
            $inherit = if ($Directory) { 'ContainerInherit, ObjectInherit' } else { 'None' }
            $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', $inherit, 'None', 'Allow')
            $acl.AddAccessRule($rule)
            Set-Acl -LiteralPath $Path -AclObject $acl
        } else {
            $mode = if ($Directory) { '700' } else { '600' }
            & chmod $mode -- $Path
            if ($LASTEXITCODE -ne 0) { throw 'Cannot protect private storage.' }
        }
    }
    function Write-PrivateBytes([string]$Path, [byte[]]$Bytes) {
        $temporary = Join-Path (Split-Path -Parent $Path) ('.private-' + [guid]::NewGuid().ToString('N'))
        try {
            [IO.File]::WriteAllBytes($temporary, [byte[]]@())
            Protect-PrivatePath $temporary $false
            [IO.File]::WriteAllBytes($temporary, $Bytes)
            Move-Item -LiteralPath $temporary -Destination $Path -Force
        } finally { Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue }
    }
    # Reject linked ancestors as well as linked files before reading any private data.
    foreach ($path in @($store, $config, $keyFile, $baseline)) {
        $cursor = $path
        while ($cursor) {
            if (Test-Path -LiteralPath $cursor) {
                if ((Get-Item -LiteralPath $cursor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unsafe private configuration path.' }
            }
            $cursor = Split-Path -Parent $cursor
        }
    }
    New-Item -ItemType Directory -Path $store -Force | Out-Null
    Protect-PrivatePath $store $true
    if ($Action -eq 'login') {
        if ([Console]::IsInputRedirected) { $value = [Console]::ReadLine() }
        else {
            $secure = Read-Host 'Key' -AsSecureString
            $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try { $value = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $secure.Dispose() }
        }
        if (!$value -or $value -match '[^\x21-\x7e]|[{}]') { throw 'A nonempty key without whitespace, control characters or braces is required.' }
        Write-PrivateBytes $keyFile ($utf8.GetBytes($value))
        Write-Output 'Key saved in private storage.'
        return
    }
    if ($Action -in @('off', 'logout')) {
        if (Test-Path -LiteralPath $baseline) {
            Protect-PrivatePath (Split-Path -Parent $config) $true
            Write-PrivateBytes $config ([IO.File]::ReadAllBytes($baseline))
            Remove-Item -LiteralPath $baseline -Force
        }
        if ($Action -eq 'logout') {
            Remove-Item -LiteralPath $keyFile -Force -ErrorAction SilentlyContinue
            Write-Output 'Key removed from private storage.'
        }
        return
    }
    $url = $env:AI4SCIENCE_PWM_URL
    $uri = $null
    if (!$url -or ![Uri]::TryCreate($url, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -ne 'https' -or !$uri.Host -or $uri.UserInfo -or $uri.Fragment -or $url -match '[\s{}\\]') {
        throw 'AI4SCIENCE_PWM_URL must be set to an https URL for a remote MCP server.'
    }
    if (!(Test-Path -LiteralPath $keyFile -PathType Leaf)) { throw 'No saved key; run ai4science pwm login first.' }
    Protect-PrivatePath $keyFile $false
    $value = [IO.File]::ReadAllText($keyFile)
    if (!$value -or $value -match '[^\x21-\x7e]|[{}]') { throw 'Saved key is invalid; run ai4science pwm login again.' }
    $original = if (Test-Path -LiteralPath $baseline) { [IO.File]::ReadAllBytes($baseline) } else { [IO.File]::ReadAllBytes($config) }
    $settings = $utf8.GetString($original) | ConvertFrom-Json
    if (!$settings.mcp) { $settings | Add-Member -NotePropertyName mcp -NotePropertyValue ([pscustomobject]@{}) -Force }
    $settings.mcp | Add-Member -NotePropertyName pwm -NotePropertyValue ([pscustomobject]@{
        type = 'remote'; url = $url; enabled = $true; oauth = $false
        headers = @{ Authorization = ('Bearer ' + $value) }
    }) -Force
    $instruction = Join-Path $Prefix 'share/agent/pwm-loop.md'
    if (!(Test-Path -LiteralPath $instruction -PathType Leaf)) { throw 'Remote workflow instruction is missing; reinstall the wrapper.' }
    $instructions = @()
    if ($settings.instructions) { $instructions = @($settings.instructions) }
    $settings | Add-Member -NotePropertyName instructions -NotePropertyValue @($instructions + $instruction) -Force
    Protect-PrivatePath (Split-Path -Parent $config) $true
    if (!(Test-Path -LiteralPath $baseline)) { Write-PrivateBytes $baseline $original }
    Write-PrivateBytes $config ($utf8.GetBytes(($settings | ConvertTo-Json -Depth 100) + "`n"))
}

param(
    [int]$ApiPort = 8787,
    [int]$WebPort = 8001
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$WebappRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$LogDir = Join-Path $WebappRoot "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null

$ApiOut = Join-Path $LogDir "api.stdout.log"
$ApiErr = Join-Path $LogDir "api.stderr.log"
$WebOut = Join-Path $LogDir "vite.stdout.log"
$WebErr = Join-Path $LogDir "vite.stderr.log"

$Utf8Prefix = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); `$OutputEncoding = [System.Text.UTF8Encoding]::new();"

$Api = Start-Process -FilePath "powershell.exe" `
    -WorkingDirectory $WebappRoot `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $ApiOut `
    -RedirectStandardError $ApiErr `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "$Utf8Prefix python -m uvicorn backend.app:app --host 127.0.0.1 --port $ApiPort"
    )

$Web = Start-Process -FilePath "powershell.exe" `
    -WorkingDirectory $WebappRoot `
    -WindowStyle Hidden `
    -PassThru `
    -RedirectStandardOutput $WebOut `
    -RedirectStandardError $WebErr `
    -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "$Utf8Prefix npm run dev -- --host 127.0.0.1 --port $WebPort"
    )

Start-Sleep -Seconds 3

[pscustomobject]@{
    ApiUrl = "http://127.0.0.1:$ApiPort/api/health"
    WebUrl = "http://127.0.0.1:$WebPort"
    ApiWrapperPid = $Api.Id
    WebWrapperPid = $Web.Id
    Logs = $LogDir
} | ConvertTo-Json

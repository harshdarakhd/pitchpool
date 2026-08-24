# Installs a Windows logon task that keeps PitchPool fixtures in sync.
# CricHeroes blocks Render's IP; this PC scrapes and pushes to the live site.
#
# Usage (from repo root, PowerShell):
#   .\scripts\install_sync_agent.ps1
#   .\scripts\install_sync_agent.ps1 -Uninstall

param(
    [switch]$Uninstall,
    [string]$SiteUrl = "https://pitchpool.onrender.com",
    [string]$CronSecret = "",
    [int]$IntervalSeconds = 600
)

$ErrorActionPreference = "Stop"
$TaskName = "PitchPoolSyncAgent"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $RepoRoot "backend"
$AgentEnv = Join-Path $Backend ".env.agent"
$LogFile = Join-Path $Backend "sync_agent.log"
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Python) { throw "Python is not on PATH. Install Python 3.12+ and retry." }

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task $TaskName"
    exit 0
}

if (-not $CronSecret) {
    $secretFile = Join-Path $RepoRoot ".cron_secret.local"
    if (Test-Path $secretFile) {
        $CronSecret = (Get-Content $secretFile -Raw).Trim()
    }
}
if (-not $CronSecret) {
    $CronSecret = Read-Host "Paste CRON_SECRET from the Render dashboard"
}
if (-not $CronSecret) { throw "CRON_SECRET is required" }

@"
PITCHPOOL_URL=$SiteUrl
PITCHPOOL_CRON_SECRET=$CronSecret
"@ | Set-Content -Path $AgentEnv -Encoding ascii

$cmd = @"
`$envFile = '$AgentEnv'
Get-Content `$envFile | ForEach-Object {
  if (`$_ -match '^([^#=]+)=(.*)$') { Set-Item -Path env:`$(`$matches[1]) -Value `$matches[2] }
}
Set-Location '$Backend'
`$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path `$env:LOCALAPPDATA 'ms-playwright'
& '$Python' scripts\push_sync.py --loop --interval $IntervalSeconds *>> '$LogFile'
"@
$encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cmd))
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -EncodedCommand $encoded"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Installed $TaskName (runs at logon, every $IntervalSeconds seconds, and when you tap Sync on your phone)."
Write-Host "Leave this PC on and signed in. Log: $LogFile"
Write-Host "Uninstall: .\scripts\install_sync_agent.ps1 -Uninstall"

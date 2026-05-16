# CSIS 24/7 daemon launcher (PowerShell, restart-on-crash).
#
# Usage:
#   .\scripts\run_daemon.ps1                  # mock backend, unlimited
#   .\scripts\run_daemon.ps1 -Backend anthropic -RatePerHour 30
#   .\scripts\run_daemon.ps1 -MaxIter 1000
#
# Stop:
#   New-Item -ItemType File .\STOP            # drop a STOP file
#   (the daemon checks every tick and exits cleanly)
#
# Survive reboots:
#   Open Task Scheduler -> Create Task -> Trigger: At log on (or At startup)
#   Action: pwsh.exe -File "<repo>\scripts\run_daemon.ps1"
#   Working dir: "<repo>"
#   Or use nssm if you want it as a true Windows service.

param(
    [string]$Backend = "mock",
    [int]$RatePerHour = 60,
    [double]$SleepS = 1.0,
    [int]$SnapshotEvery = 25,
    [int]$MaxIter = 0,  # 0 = unlimited
    [int]$RestartCooldownS = 5
)

$ErrorActionPreference = "Stop"

# Resolve repo root from this script's location.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

# Make sure the log dir exists.
$LogDir = Join-Path $RepoRoot "brain\daemon_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

# Build the argument list.
$pyArgs = @("-u", "-m", "csis.daemon",
            "--backend", $Backend,
            "--rate-per-hour", "$RatePerHour",
            "--sleep-s", "$SleepS",
            "--snapshot-every", "$SnapshotEvery")
if ($MaxIter -gt 0) {
    $pyArgs += @("--max-iter", "$MaxIter")
}

Write-Host "[csis.daemon launcher] starting"
Write-Host "  repo:    $RepoRoot"
Write-Host "  backend: $Backend"
Write-Host "  rate:    $RatePerHour/h, sleep $SleepS s"
Write-Host "  stop:    drop a STOP file in $RepoRoot"
Write-Host ""

# Restart-on-crash loop.
while ($true) {
    $StopFile = Join-Path $RepoRoot "STOP"
    if (Test-Path $StopFile) {
        Write-Host "[csis.daemon launcher] STOP file present; exiting."
        break
    }

    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $LogPath = Join-Path $LogDir "daemon-$Stamp.log"
    Write-Host "[csis.daemon launcher] $(Get-Date -Format o) launching python; log -> $LogPath"

    # Run synchronously; stdout+stderr captured to the log.
    & python @pyArgs *>&1 | Tee-Object -FilePath $LogPath
    $rc = $LASTEXITCODE
    Write-Host "[csis.daemon launcher] python exited rc=$rc"

    if (Test-Path $StopFile) {
        Write-Host "[csis.daemon launcher] STOP file present; not restarting."
        break
    }

    Write-Host "[csis.daemon launcher] restarting in $RestartCooldownS seconds..."
    Start-Sleep -Seconds $RestartCooldownS
}

Write-Host "[csis.daemon launcher] done."

# Install CSIS daemon as a Windows service via NSSM.
#
# Prereqs:
#   - NSSM installed and on PATH (choco install nssm, or download from nssm.cc)
#   - Python on PATH (or pass -PythonExe)
#   - Run this script from an elevated (Administrator) PowerShell.
#
# Usage:
#   .\scripts\install_service.ps1
#   .\scripts\install_service.ps1 -Backend mock -RatePerHour 30
#   .\scripts\install_service.ps1 -PythonExe "C:\Python311\python.exe"
#
# Verify:
#   sc.exe query CSIS
#   Get-Content .\brain\daemon.heartbeat
#
# Stop the service (one-off):
#   sc.exe stop CSIS
#   New-Item -ItemType File .\STOP   # graceful — daemon checks every tick
#
# Uninstall:
#   .\scripts\uninstall_service.ps1

param(
    [string]$ServiceName = "CSIS",
    [string]$PythonExe = "python",
    [string]$Backend = "mock",
    [int]$RatePerHour = 60,
    [double]$SleepS = 1.0,
    [int]$SnapshotEvery = 25,
    [string]$Domain = "",
    [string]$RepoPath = "",
    [switch]$StartNow  # synthesis gap #7: skip the interactive prompt for unattended setup
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

# Sanity: nssm available?
$nssm = Get-Command nssm -ErrorAction SilentlyContinue
if (-not $nssm) {
    Write-Error "nssm not found on PATH. Install with 'choco install nssm' or download from https://nssm.cc and add to PATH."
    exit 1
}

# Build the argument string for the python -m csis.daemon invocation.
$daemonArgs = @("-u", "-m", "csis.daemon",
                "--backend", $Backend,
                "--rate-per-hour", "$RatePerHour",
                "--sleep-s", "$SleepS",
                "--snapshot-every", "$SnapshotEvery")
if ($Domain -ne "") {
    $daemonArgs += @("--domain", $Domain)
}
if ($RepoPath -ne "") {
    $daemonArgs += @("--repo-path", $RepoPath)
}
$daemonArgStr = ($daemonArgs -join " ")

Write-Host "[install_service] service: $ServiceName"
Write-Host "[install_service] repo:    $RepoRoot"
Write-Host "[install_service] python:  $PythonExe"
Write-Host "[install_service] args:    $daemonArgStr"
Write-Host ""

# Install (or reconfigure) the service.
& nssm install $ServiceName $PythonExe $daemonArgStr
& nssm set $ServiceName AppDirectory $RepoRoot
& nssm set $ServiceName DisplayName "CSIS Phase-0 Daemon"
& nssm set $ServiceName Description "Continuous self-improving system daemon (csis.daemon). Stop via STOP file in repo root or 'sc.exe stop $ServiceName'."
& nssm set $ServiceName Start SERVICE_AUTO_START

# Pipe stdout/stderr to dated logs under brain/service_logs/.
$LogDir = Join-Path $RepoRoot "brain\service_logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
& nssm set $ServiceName AppStdout (Join-Path $LogDir "$ServiceName.out.log")
& nssm set $ServiceName AppStderr (Join-Path $LogDir "$ServiceName.err.log")
& nssm set $ServiceName AppRotateFiles 1
& nssm set $ServiceName AppRotateBytes 5242880

Write-Host ""
Write-Host "[install_service] installed. Start with: sc.exe start $ServiceName"
Write-Host "[install_service] verify with: sc.exe query $ServiceName"
Write-Host "[install_service] watch heartbeat: Get-Content .\brain\daemon.heartbeat"
Write-Host "[install_service] stop gracefully: New-Item -ItemType File .\STOP"
Write-Host ""
if ($StartNow) {
    Write-Host "[install_service] -StartNow set; starting now without prompt."
    & sc.exe start $ServiceName
    & sc.exe query $ServiceName
} else {
    Write-Host "Start now? (y/n)  (or re-run with -StartNow for unattended install)"
    $reply = Read-Host
    if ($reply -eq "y" -or $reply -eq "Y") {
        & sc.exe start $ServiceName
        & sc.exe query $ServiceName
    }
}

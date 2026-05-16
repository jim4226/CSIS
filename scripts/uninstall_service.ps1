# Uninstall the CSIS NSSM service.
#
# Usage:
#   .\scripts\uninstall_service.ps1
#   .\scripts\uninstall_service.ps1 -ServiceName CSIS

param(
    [string]$ServiceName = "CSIS"
)

$ErrorActionPreference = "Continue"

Write-Host "[uninstall_service] stopping $ServiceName"
& sc.exe stop $ServiceName 2>$null

# Drop a STOP file so any current iteration exits gracefully.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$StopFile = Join-Path $RepoRoot "STOP"
if (-not (Test-Path $StopFile)) {
    New-Item -ItemType File -Path $StopFile -Force | Out-Null
}

Write-Host "[uninstall_service] removing service"
& nssm remove $ServiceName confirm

Write-Host "[uninstall_service] cleaning STOP file"
Remove-Item $StopFile -ErrorAction SilentlyContinue

Write-Host "[uninstall_service] done. Brain/event_log/memory_store left intact."

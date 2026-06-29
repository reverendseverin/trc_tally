# Install TRC Tally as a Windows service using NSSM (https://nssm.cc/).
# Run from an elevated PowerShell. Requires nssm.exe on PATH (or pass -Nssm).
#
#   .\install-service.ps1 -ExePath "C:\TRCTally\TRC_Tally_Cloud_Client.exe"

param(
    [Parameter(Mandatory = $true)] [string]$ExePath,
    [string]$ServiceName = "TRCTally",
    [string]$Nssm = "nssm"
)

if (-not (Test-Path $ExePath)) {
    Write-Error "Executable not found: $ExePath"; exit 1
}
$AppDir = Split-Path -Parent $ExePath

& $Nssm install $ServiceName $ExePath
& $Nssm set $ServiceName AppDirectory $AppDir
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStdout (Join-Path $AppDir "service.log")
& $Nssm set $ServiceName AppStderr (Join-Path $AppDir "service.log")
& $Nssm start $ServiceName

Write-Host "Installed and started '$ServiceName'. Web UI: http://localhost:8070"
Write-Host "Remove with:  $Nssm stop $ServiceName ; $Nssm remove $ServiceName confirm"

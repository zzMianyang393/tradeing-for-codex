# Scheduled local majors job: refresh BTC/ETH 15m (commit) then paper cycle.
# Never places OKX demo/live orders.
# Example Task Scheduler action:
#   powershell -NoProfile -ExecutionPolicy Bypass -File E:\ai-trade\tradering\scripts\prod_majors_hourly.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

$OutDir = Join-Path $RepoRoot "reports\prod"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $OutDir "majors_hourly_$Stamp.log"

function Write-Log([string]$Msg) {
    $line = "{0} {1}" -f (Get-Date -Format "o"), $Msg
    Add-Content -Path $Log -Value $line
    Write-Host $line
}

Write-Log "START majors hourly job"
& python -m prod.cli majors-hourly --commit-refresh 2>&1 | Tee-Object -FilePath $Log -Append
$code = $LASTEXITCODE
Write-Log "END exit=$code"
exit $code

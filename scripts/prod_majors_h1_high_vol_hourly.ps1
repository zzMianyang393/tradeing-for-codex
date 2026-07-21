# Scheduled local paper for admitted 1h high-vol donchian short sleeve.
# Never places OKX demo/live orders.
# Example Task Scheduler:
#   powershell -NoProfile -ExecutionPolicy Bypass -File E:\ai-trade\tradering\scripts\prod_majors_h1_high_vol_hourly.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

$OutDir = Join-Path $RepoRoot "reports\prod"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $OutDir "majors_h1_high_vol_hourly_$Stamp.log"

function Write-Log([string]$Msg) {
    $line = "{0} {1}" -f (Get-Date -Format "o"), $Msg
    Add-Content -Path $Log -Value $line
    Write-Host $line
}

Write-Log "START h1 high_vol_donchian_short hourly"
& python -m prod.cli majors-hourly `
  --strategy-id prod_majors_h1_high_vol_donchian_short_v1 `
  --state reports/prod/h1_high_vol_donchian_short_paper_state.json `
  --cycle-out reports/prod/h1_high_vol_donchian_short_paper_cycle.json `
  --lock reports/prod/h1_high_vol_donchian_short_runtime.lock `
  --out reports/prod/h1_high_vol_donchian_short_hourly_job.json `
  --commit-refresh 2>&1 | Tee-Object -FilePath $Log -Append
$code = $LASTEXITCODE
Write-Log "END exit=$code"
exit $code

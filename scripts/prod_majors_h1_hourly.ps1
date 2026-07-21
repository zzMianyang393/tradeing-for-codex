# Scheduled local 1h research sleeve job:
#   refresh BTC/ETH 1H (commit) then paper for prod_majors_h1_md_mom_short_v1
# Never places OKX demo/live orders.
# Example Task Scheduler action:
#   powershell -NoProfile -ExecutionPolicy Bypass -File E:\ai-trade\tradering\scripts\prod_majors_h1_hourly.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$env:PYTHONPATH = $RepoRoot

$OutDir = Join-Path $RepoRoot "reports\prod"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $OutDir "majors_h1_hourly_$Stamp.log"

function Write-Log([string]$Msg) {
    $line = "{0} {1}" -f (Get-Date -Format "o"), $Msg
    Add-Content -Path $Log -Value $line
    Write-Host $line
}

Write-Log "START majors h1 md_mom_short hourly job"
& python -m prod.cli majors-hourly `
  --strategy-id prod_majors_h1_md_mom_short_v1 `
  --state reports/prod/h1_md_mom_short_paper_state.json `
  --cycle-out reports/prod/h1_md_mom_short_paper_cycle.json `
  --lock reports/prod/h1_md_mom_short_runtime.lock `
  --out reports/prod/h1_md_mom_short_hourly_job.json `
  --commit-refresh 2>&1 | Tee-Object -FilePath $Log -Append
$code = $LASTEXITCODE
Write-Log "END exit=$code"
exit $code

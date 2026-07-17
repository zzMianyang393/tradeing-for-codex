# Remove bulky local artifacts from the git INDEX only (files stay on disk).
# Run from repo root. Review `git status` before committing.
$ErrorActionPreference = "Continue"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $root
if (-not (Test-Path ".git")) { Write-Error "Not a git repo: $root"; exit 1 }
Write-Host "Working directory: $(Get-Location)"
Write-Host "Untracking data/, reports/, pytest caches (local files kept)..."
git rm -r --cached data 2>$null
git rm -r --cached reports 2>$null
Get-ChildItem -Directory -Filter "pytest_tmp*" -ErrorAction SilentlyContinue | ForEach-Object {
    git rm -r --cached $_.Name 2>$null
}
git rm -r --cached __pycache__ 2>$null

git add .gitignore
git add prod
git add docs/PRODUCTION_TRACK.md
git add docs/REPO_SLIM_GITHUB.md
git add docs/SYSTEM_ROADMAP_AND_SLIM_PLAN.md
git add README.md
git add tests/test_prod_admission.py
git add tests/test_prod_registry.py
git add tests/test_prod_slim_paths.py
git add tests/test_prod_universe_check.py
git add tests/test_prod_ten_u_market_refresh.py
git add scripts/slim_git_for_github.ps1

Write-Host ""
Write-Host "Index cleaned for bulk paths. Next:"
Write-Host "  git status"
Write-Host "  git commit -m `"chore: slim github tracking; prod paper-prep track`""
Write-Host "  git push origin main"
Write-Host "Force-push is NOT required."

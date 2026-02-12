# verify.ps1 - Full verification (lint + format + unit + integration tests)
# Purpose: Run before PR/merge (~1-2 minutes)

$ErrorActionPreference = "Stop"

Write-Host "==> Running verify-fast..." -ForegroundColor Cyan
& "$PSScriptRoot\verify-fast.ps1"
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> integration tests" -ForegroundColor Cyan
uv run python -m dotenv -f .env.test run -- pytest tests/integration -q
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "verify PASSED (full suite)" -ForegroundColor Green
exit 0

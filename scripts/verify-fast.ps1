#Requires -Version 5.1
# verify-fast.ps1 - Quick verification (lint + format + unit tests)
# Purpose: Fast feedback on every change (~10-30 seconds)

$ErrorActionPreference = "Stop"

Write-Host "==> ruff check (lint)" -ForegroundColor Cyan
uv run ruff check src tests
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> ruff format --check" -ForegroundColor Cyan
uv run ruff format --check src tests
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "==> unit tests" -ForegroundColor Cyan
uv run pytest tests/unit -q
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "verify-fast PASSED" -ForegroundColor Green
exit 0

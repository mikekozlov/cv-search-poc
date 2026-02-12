#Requires -Version 5.1
# stop-verify.ps1 - Claude Code Stop hook
# Blocks Claude from finishing until verify-fast passes
# Exit code 2 = blocking error (stderr fed back to Claude)

# Change to project directory
Set-Location $env:CLAUDE_PROJECT_DIR

# Skip verification if no uncommitted changes
$gitStatus = git status --porcelain
if (-not $gitStatus) {
    exit 0
}

# Run verify-fast and capture output
$tempFile = [System.IO.Path]::GetTempFileName()
try {
    & "$env:CLAUDE_PROJECT_DIR\scripts\verify-fast.ps1" *> $tempFile 2>&1
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0) {
        exit 0
    }

    # Verification failed - output error to stderr and exit 2 to block
    Write-Error "verify-fast FAILED. Fix the issues and try again."
    Write-Error "---- last 120 lines ----"
    Get-Content $tempFile -Tail 60 | ForEach-Object { Write-Error $_ }

    # Exit 2 = blocking error, stderr goes back to Claude
    exit 2
}
finally {
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}

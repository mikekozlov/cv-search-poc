---
name: e2e-api-test
description: |
  Verifier Agent: end-to-end API verification with dynamic checks for response and DB state.
  Starts real FastAPI server with OpenAI stub mode, calls endpoints, verifies
  responses and database state.
  Use when: testing new/modified API endpoints, E2E verification, endpoint validation.
allowed-tools: Bash, Read, Write, Grep, Glob, Edit, mcp__db-cv-search__query
---

# Verifier Agent (E2E API Test Skill)

Runs the full end-to-end verification loop with dynamic check selection based on what changed.

## Dynamic Verification Checklist

Before starting, analyze the code changes (git diff or plan) to determine which checks to run:

```
Router/endpoint added/modified?
  -> YES: API verification (server + call + response check)
  -> NO:  Skip E2E, report "No endpoint changes detected"

Database/SQL added/modified?
  -> YES: DB verification (query after call, compare expected state)

API call returned error or unexpected response?
  -> YES: Check server stderr logs for traceback
```

Build this checklist at the start and track which checks pass/fail.

## Session State

Track state in `$env:TEMP\cvsearch-e2e-state.json`:

```json
{
  "apiPid": null,
  "attemptCount": 0,
  "logFiles": [],
  "checklist": {
    "api": { "enabled": true, "status": "pending" },
    "db": { "enabled": false, "status": "pending" }
  },
  "failureHistory": []
}
```

The `failureHistory` array stores failure signatures from each retry attempt. Used by the Duplicate Failure Detection mechanism to avoid repeating the same failing fix.

## Retry State Machine

```
[LINT_CHECK] ----fail----> [FIX_LINT] --> [LINT_CHECK]              (max 3)
  |
  v pass
[START_SERVER] --fail-> [FIX_STARTUP] --> [LINT_CHECK]              (max 3)
  |
  v pass
[CALL_ENDPOINT] --exception in console--> [FIX_RUNTIME] --> [LINT_CHECK]  (max 5 total)
  |
  v pass
[VERIFY_RESPONSE] --wrong data--> [FIX_LOGIC] --> [LINT_CHECK]           (max 5 total)
  |
  v pass
[VERIFY_DB] --wrong state--> [FIX_PERSISTENCE] --> [LINT_CHECK]          (max 5 total)
  |
  v pass
[CLEANUP] --> [REPORT_SUCCESS]
```

**On ANY failure after max retries**: CLEANUP -> REPORT_FAILURE

### Duplicate Failure Detection (Hard Stop)

After every fix attempt, compute a **failure signature**:
- Format: `{state}:{error_type}:{error_message_prefix}:{file_or_location}`
- Example: `FIX_LINT:E302:expected 2 blank lines:src/cv_search/api/search/router.py:42`
- Example: `FIX_RUNTIME:AttributeError:object has no attribute:src/cv_search/search/processor.py:87`

**Rules**:
1. Record each failure signature in the E2E session state's `failureHistory` array
2. Before applying a fix, check if the **same signature** already appeared in `failureHistory`
3. If the same signature appears **twice consecutively**:
   - **STOP immediately** — do not burn remaining retries
   - Proceed to CLEANUP
   - Report as `BLOCKED` instead of `FAILED`:
     ```
     ## E2E Verification: BLOCKED
     - Endpoint: {METHOD} {PATH}
     - Blocked at: {state name}
     - Duplicate failure: {signature}
     - Attempts before block: {count}
     - Last fix tried: {description}
     - This error persisted after a fix attempt. The root cause was likely misidentified.
     ```
   - Return findings to the Developer Agent with the blocker details
4. This prevents wasting 5 retries on the same misidentified root cause

## Instructions

### Prerequisites

Before starting E2E verification, ensure:
1. Code changes are implemented
2. Unit tests pass
3. You know: endpoint method, path, required headers, expected response shape

### Phase 1: Lint Check

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
```

If lint fails:
- Parse error output for file:line and rule code
- Fix the code
- Retry (max 3 attempts)

### Phase 2: Start API Server

```powershell
$tempDir = "$env:TEMP\cvsearch-e2e"
if (-not (Test-Path $tempDir)) { New-Item -ItemType Directory -Path $tempDir -Force }

$env:USE_OPENAI_STUB = "1"
$proc = Start-Process -NoNewWindow -FilePath "uv" `
  -ArgumentList "run","uvicorn","cv_search.api.main:app","--host","127.0.0.1","--port","8000" `
  -RedirectStandardOutput "$tempDir\api-stdout.log" `
  -RedirectStandardError "$tempDir\api-stderr.log" `
  -PassThru

# Save PID to state
$proc.Id
```

**Wait for startup** (max 30 seconds):
```powershell
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) { break }
    } catch {}
    Start-Sleep -Seconds 2
    $waited += 2
}
```

If server fails to start:
- Read stderr log for exception details
- Common issues: missing DI registration, config errors, port in use
- Fix, re-lint, and retry (max 3 attempts)

### Phase 3: Call Endpoint

```powershell
$headers = @{
    "Content-Type" = "application/json"
}

# Add API key if configured
if ($env:API_KEY) {
    $headers["X-API-Key"] = $env:API_KEY
}

$response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/{path}" `
  -Method {METHOD} -Headers $headers -Body $body
```

After the call, **immediately check** API stderr for exceptions:
```powershell
$stderr = Get-Content "$env:TEMP\cvsearch-e2e\api-stderr.log" -ErrorAction SilentlyContinue
if ($stderr -match "Traceback|Exception|Error") {
    # Exception detected - enter FIX_RUNTIME
}
```

### Phase 4: Verify Response

Compare actual response against expected response shape defined in the plan:
- Check status code
- Check required fields exist
- Check field values match expectations
- Check array lengths if specified

If response doesn't match:
- Read router, processor/service, and database code to find the issue
- Fix logic, re-lint, restart, retry

### Phase 5: Verify Database State (if checklist.db.enabled)

Use `mcp__db-cv-search__query` to run verification queries specified in the plan.

Compare actual database state against expected state:
- Check rows exist
- Check column values
- Check timestamps are recent

If database state doesn't match:
- Read database method and service code
- Fix persistence logic, re-lint, restart, retry

### Phase 6: Cleanup (MANDATORY)

**This phase runs on EVERY exit path - success, failure, or error.**

```powershell
# 1. Stop API server
$state = Get-Content "$env:TEMP\cvsearch-e2e-state.json" | ConvertFrom-Json
if ($state.apiPid) {
    Stop-Process -Id $state.apiPid -Force -ErrorAction SilentlyContinue
}

# 2. Delete state file
Remove-Item "$env:TEMP\cvsearch-e2e-state.json" -Force -ErrorAction SilentlyContinue

# 3. Delete log files
Remove-Item "$env:TEMP\cvsearch-e2e\api-stdout.log" -Force -ErrorAction SilentlyContinue
Remove-Item "$env:TEMP\cvsearch-e2e\api-stderr.log" -Force -ErrorAction SilentlyContinue

# 4. Verify port is free
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

**Cleanup triggers (NEVER skip)**:
1. All verifications pass -> cleanup -> report success
2. Max retries exceeded -> cleanup -> report failure with diagnostics
3. Lint fails repeatedly -> cleanup -> report lint failure
4. No test data found -> cleanup -> report data issue
5. User cancels -> cleanup -> confirm clean state

## Fix Step Guidance

| State | Approach |
|-------|----------|
| FIX_LINT | Parse `ruff check` errors (missing import, formatting). Fix is localized to reported file:line. |
| FIX_STARTUP | Read stderr log. Common: missing dependency injection in `api/deps.py`, config key missing in Settings, port in use. |
| FIX_RUNTIME | Read traceback from stderr. Map exception to source file. Trace router → service → database code. |
| FIX_LOGIC | Compare actual vs expected response. Read router, processor/service, and database code. |
| FIX_PERSISTENCE | Compare expected DB state vs actual. Read database methods in `db/database.py`. |

## Report Format

### Success
```
## E2E Verification: PASSED
- Endpoint: {METHOD} {PATH}
- Response: {status code} - matches expected shape
- Checklist:
  - [x] API response verified
  - [x] Database state verified (if enabled)
- Attempts: {count}
- Stub mode: USE_OPENAI_STUB=1
```

### Failure
```
## E2E Verification: FAILED
- Endpoint: {METHOD} {PATH}
- Failed at: {state name}
- Error: {description}
- Checklist:
  - [x] API response verified
  - [ ] Database state FAILED: {details}
- Attempts: {count}/{max}
- Last error output: {relevant logs}
```

### Findings

After verification (pass or fail), compile a findings list for the Developer Agent:

```
## Verification Findings
1. [PASS] API response matches expected shape
2. [PASS] Database row created with correct values
3. [WARN] Response missing optional field 'justification'
4. [FAIL] Database state does not match expected schema
```

Each finding includes:
- Status: PASS, WARN, FAIL
- Description of what was checked
- For WARN/FAIL: details of the discrepancy

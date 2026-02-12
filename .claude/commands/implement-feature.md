# Implement Feature

Developer Agent: parses a plan, implements the feature with evidence-first discovery, runs unit tests, delegates E2E verification to the Verifier Agent, and prompts for skill enhancement.

Follows the **5-step framework**: UNDERSTAND -> ANALYZE -> IMPLEMENT -> VERIFY -> CONCLUDE

## Prerequisites

This command expects a plan file produced during **Plan Mode**. The typical workflow is:

1. User describes the feature in plain English
2. Claude enters Plan Mode (automatically or via `/plan`) — explores codebase, asks questions, writes plan
3. User reviews and approves the plan
4. User runs `/implement-feature` with the approved plan

Step 1 (UNDERSTAND) validates the plan against the current codebase state before any code is written.

## Usage

```
/implement-feature {plan-file-path}
```

The argument is a path to a plan file (markdown). If no argument is provided, look for the most recently modified `.md` file in `.claude/plans/`.

## Feature State Persistence

Track progress in `$env:TEMP\cvsearch-feature-state\{feature-id}.json` so work survives context compaction and session restarts.

### State File Schema

```json
{
  "featureId": "add-health-detail-endpoint",
  "planPath": ".claude/plans/health-detail.md",
  "startedAtUtc": "2026-02-08T10:00:00Z",
  "updatedAtUtc": "2026-02-08T10:30:00Z",
  "currentStep": "IMPLEMENT",
  "tasks": [
    {
      "id": "TASK-01",
      "description": "Add health detail router",
      "status": "completed",
      "attempts": 1,
      "lastFailureSignature": null
    },
    {
      "id": "TASK-02",
      "description": "Add database health check method",
      "status": "in-progress",
      "attempts": 2,
      "lastFailureSignature": "lint_error:E302:expected 2 blank lines:src/cv_search/db/database.py:42"
    }
  ],
  "verification": {
    "lintStatus": "passed",
    "unitTestStatus": "passed",
    "e2eStatus": "pending",
    "codeReviewStatus": "pending"
  },
  "failureHistory": [],
  "stopReason": null
}
```

### State Management Rules

1. **Create state** at the start of Step 1 (UNDERSTAND) — derive `featureId` from branch name or plan filename
2. **Update state** after each task status change, lint, test, or verification outcome
3. **Read state** at the start to detect resume scenario (see `/resume-feature`)
4. **Delete state** only after successful CONCLUDE step
5. **Preserve on failure** — keep state file with `stopReason` set for later resume

## Instructions

### Step 1: UNDERSTAND — Parse Plan, State Goals, Initialize State

Read the plan file: `$input`

**1a: Check for existing state** (resume detection):
```powershell
$stateDir = "$env:TEMP\cvsearch-feature-state"
# Look for a state file matching this plan
```
If a state file exists with `stopReason: null` and incomplete tasks -> this is a resume. Skip to the first non-completed task (see `/resume-feature` for details).

**1b: Parse plan and extract**:
1. **Core goal**: What is this feature doing? (1 sentence)
2. **Success criteria**: What must be true when done? (bullet list)
3. **Non-goals**: What are we explicitly NOT doing? (bullet list)
4. **Implementation Tasks** — if the plan has a `## Implementation Tasks` section with structured task lines, parse them:
   ```
   - [ ] TASK-01: Add database method | files: src/cv_search/db/database.py | done_when: builds and method exists
   ```
   If the plan uses free-form `## Files to Change` instead, convert each file entry into a task line.
5. **Verification Profile** — one of: `unit-only`, `e2e-light`, `e2e-full`, `e2e-mutation`
6. **Endpoint Details** (if E2E) — method, path, request body shape, expected response
7. **Test Data Queries** (if E2E) — SQL to find suitable test records via `mcp__db-cv-search__query`
8. **Database Verification Queries** (if E2E mutation) — SQL to verify state after call
9. **Acceptance Criteria** — specific conditions that must be met

**1c: Initialize state file**:
```powershell
$stateDir = "$env:TEMP\cvsearch-feature-state"
if (-not (Test-Path $stateDir)) { New-Item -ItemType Directory -Path $stateDir -Force }
```
Create `$stateDir\{feature-id}.json` with all parsed tasks set to `status: "pending"`.

If the plan doesn't have a `## Verification Profile` section, classify it:
```
Does the feature add/modify a FastAPI router endpoint?
  NO  -> unit-only (lint + unit tests only)
  YES -> Does the endpoint route through SearchProcessor/Planner (which call OpenAI)?
    NO  -> e2e-light (server + call + verify response)
    YES -> Does the endpoint write to search_run or modify candidate data?
      NO  -> e2e-full (server + call + verify response, USE_OPENAI_STUB=1)
      YES -> e2e-mutation (e2e-full + database state verification)
```

### Step 2: ANALYZE — Evidence-First Discovery

**BEFORE writing any code**, gather evidence:

1. **Search the repo** for related patterns:
   - Find similar features (e.g., if adding a new search endpoint, find existing search routers)
   - Read how they're structured: router -> processor/service -> database -> client
   - Note naming conventions, dependency injection patterns, Pydantic model conventions

2. **Read configuration**:
   - Check `.env` / `.env.example` for relevant config sections
   - Check `src/cv_search/config/settings.py` (Settings class) for existing settings
   - Check `src/cv_search/api/deps.py` for dependency injection patterns
   - Check `src/cv_search/api/main.py` for lifespan and middleware setup

3. **Trace dependencies**:
   - For OpenAI calls: find the client methods in `src/cv_search/clients/`
   - For database: find existing methods in `src/cv_search/db/database.py`
   - For search: trace through `src/cv_search/search/processor.py`

4. **Identify constraints**:
   - Database column types and constraints (see `src/cv_search/db/schema_pg.sql`)
   - API contracts (Pydantic request/response models)
   - Business rules from existing code

**Output**: A brief analysis summary with key findings before proceeding to implementation.

### Step 3: IMPLEMENT — Write Code and Tests (Task-by-Task)

Process tasks **one at a time** in order. For each task:

1. **Update state**: set task status to `"in-progress"`, increment `attempts`
2. **Implement the task**:
   - Read existing files (if modifying)
   - Write production code following CLAUDE.md conventions
   - Write/update unit tests (pytest with plain assertions)
3. **Verify the task's `done_when` condition** (lint, specific test, etc.)
4. **Update state**: set task status to `"completed"` or record failure signature

#### Production Code Conventions
- Follow existing patterns in the codebase
- Pydantic models for API request/response schemas
- FastAPI dependency injection via `api/deps.py`
- Database methods in `CVDatabase` class
- No inline comments unless logic is non-obvious

#### Unit Test Conventions
- Arrange/Act/Assert pattern
- pytest with plain assertions (no FluentAssertions equivalent)
- Place tests in `tests/unit/` mirroring source layout
- Use `unittest.mock` for mocking dependencies

**Do NOT start the next task until the current task's `done_when` is satisfied.**

### Step 4: VERIFY — Lint, Test, and E2E

#### 4a: Lint Verification (max 3 retries)

```powershell
uv run ruff check src tests
uv run ruff format --check src tests
```

If lint fails:
1. Parse error output for file:line and rule code
2. **Record failure signature** (see Duplicate Failure Detection below)
3. Fix the code
4. Retry (max 3 attempts)
5. If still failing after 3 attempts, report failure and stop

#### 4b: Unit Test Verification (max 3 retries)

Run tests relevant to the feature:
```powershell
uv run pytest tests/unit -q -k "{pattern}"
```

If tests fail:
1. Read test output to identify failing assertions
2. **Record failure signature** (see Duplicate Failure Detection below)
3. Fix the code or tests
4. Retry (max 3 attempts)

#### 4c: E2E Verification (only if profile >= e2e-light)

**Delegate to the Verifier Agent** (e2e-api-test skill) with this context:
- Endpoint details (method, path, body)
- Expected response shape
- Test data queries
- DB verification queries
- Stub mode: `USE_OPENAI_STUB=1`

The Verifier Agent will:
1. Analyze git diff to build the dynamic verification checklist
2. Lint check
3. Start API server (with `USE_OPENAI_STUB=1`)
4. Call endpoint
5. Run all enabled checks (response, DB)
6. Cleanup
7. Return findings

Max 5 E2E retry attempts total (across Developer + Verifier Agent).

#### Duplicate Failure Detection (Hard Stop)

After every failed fix attempt, compute a **failure signature** by combining:
- Error class: `lint_error` | `test_failure` | `runtime_exception` | `wrong_response` | `wrong_db_state`
- Error identity: rule code + message (for lint), test name + assertion message (for test), exception type + message (for runtime)
- Location: file path + line number (when available)

Signature format: `{error_class}:{error_identity}:{location}`

Example: `lint_error:E302:expected 2 blank lines:src/cv_search/api/search/router.py:42`
Example: `test_failure:AssertionError:expected 3 got 2:tests/unit/test_processor.py:87`

**Rules**:
1. Record each failure signature in the state file's `failureHistory` array
2. Before applying a fix, check if the **same signature** already appears in `failureHistory`
3. If the same signature appears **twice consecutively** (same error after a fix attempt):
   - **STOP the retry loop immediately**
   - Update state: set `stopReason` to `"duplicate failure: {signature}"`
   - Report a structured blocker to the user:
     ```
     ## BLOCKED: Duplicate Failure Detected
     - Task: {TASK-ID}
     - Signature: {signature}
     - Attempts: {count}
     - Last fix tried: {description of what was changed}
     - Suggestion: This error persisted after a fix attempt, indicating the root cause
       was misidentified. Manual investigation may be needed.
     ```
   - Do NOT burn remaining retries on the same mistake
4. The state file preserves failure history, so `/resume-feature` can avoid repeating the same failed approach

#### 4d: Full Test Suite

Run the quick verification suite:
```powershell
./scripts/verify-fast.ps1
```

### Step 5: CONCLUDE — Report, Enhance, and Finalize State

#### 5a: Code Review

Run the `pre-pr-code-review` skill on the current changes. Record results for the Pre-PR Agent.

#### 5b: Finalize State

On success: update state file with all tasks `"completed"`, set `currentStep: "CONCLUDED"`, then **delete the state file** (clean exit).

On failure: keep state file intact with `stopReason` set (e.g., `"max retries exceeded at TASK-03"`) for later `/resume-feature`.

#### 5c: Implementation Summary

```markdown
## Implementation Summary

### Feature: {name}
### Goal: {1-sentence core goal}
### Verification Profile: {profile}

### Files Changed
- {file1}: {description}
- {file2}: {description}

### Tests
- New: {count}
- Modified: {count}
- All passing: Yes/No

### E2E Verification
- Endpoint: {METHOD} {PATH}
- Status: PASSED/FAILED/SKIPPED
- Checklist:
  - [x] API response verified
  - [x] Database state verified
- Attempts: {count}
- Stub mode: USE_OPENAI_STUB=1

### Code Review
- Issues found: {count}
- Details: {summary}

### Lint
- Status: PASSED
- Warnings: {count}
```

#### 5d: Skill Enhancement Prompt

After verification completes, evaluate:

1. **Did any skill fail or behave unexpectedly?**
   -> Log the issue and ask: "The `{skill}` skill failed with `{error}`. Should I update it to handle this case?"

2. **Did we discover a new pattern?**
   -> Ask: "I found that `{pattern}` (e.g., a new endpoint pattern, a new DB verification pattern). Should I add it to `{skill}`?"

3. **Did a workaround succeed?**
   -> Ask: "I worked around `{issue}` by `{workaround}`. Should I document this in `{skill}` so it works automatically next time?"

Only prompt if there's something genuinely worth recording. Don't prompt for trivial fixes.

## Plan File Format

Plans should include these sections for optimal automation:

```markdown
# Feature: {Name}

## Verification Profile
{unit-only | e2e-light | e2e-full | e2e-mutation}

## Implementation Tasks

Structured task lines with explicit completion criteria. Each task is processed
one at a time by the Developer Agent and tracked in the feature state file.

Task line format:
  - [ ] TASK-ID: description | files: path-list | done_when: observable outcome

Example:
- [ ] HEALTH-01: Add detailed health check method | files: src/cv_search/db/database.py | done_when: lint passes and method exists
- [ ] HEALTH-02: Add health detail router | files: src/cv_search/api/health/router.py | done_when: lint passes and route registered
- [ ] HEALTH-03: Add Pydantic response model | files: src/cv_search/api/health/schemas.py | done_when: lint passes
- [ ] HEALTH-04: Add unit tests | files: tests/unit/api/test_health.py | done_when: all tests pass including new ones
- [ ] HEALTH-05: Register in deps.py | files: src/cv_search/api/deps.py | done_when: lint passes and server starts

Rules:
- TASK-ID: short prefix + sequential number (e.g., HEALTH-01, SEARCH-01, INGEST-01)
- files: comma-separated paths that will be created or modified
- done_when: a testable condition (lint passes, specific test passes, server starts, etc.)
- Order matters: tasks are executed sequentially, so dependencies flow naturally

If the plan uses free-form `## Files to Change` instead, the Developer Agent will
convert each entry into a task line automatically during Step 1.

## Endpoint Details (if E2E)
- Method: POST
- Path: /api/v1/search/seat
- Request Body: { ... }
- Expected Response: { ... }

## Test Data Queries
```sql
SELECT candidate_id, name FROM candidate LIMIT 1
`` `

## Database Verification Queries
```sql
SELECT run_id, status FROM search_run ORDER BY created_at DESC LIMIT 1
`` `

## Acceptance Criteria
1. ...
2. ...
```

$input

# Resume Feature

Resume an interrupted `/implement-feature` run from its persisted state file, without redoing completed work.

## Usage

```
/resume-feature {feature-id}
```

The argument is a feature ID (e.g., `add-health-detail-endpoint`). If no argument is provided, list all state files in `$env:TEMP\cvsearch-feature-state\` and let the user pick.

## Instructions

### Step 1: Load State

```powershell
$stateDir = "$env:TEMP\cvsearch-feature-state"
$stateFile = "$stateDir\{feature-id}.json"
```

Read the state file. If it doesn't exist, report: "No state file found for `{feature-id}`. Use `/implement-feature` to start fresh."

### Step 2: Validate Plan Still Exists

Read the `planPath` from state. If the plan file is missing, report and stop.

### Step 3: Assess Resume Point

From the state file, determine:

1. **Last completed task**: The most recent task with `status: "completed"`
2. **Current task**: The first task with `status: "in-progress"` or `status: "pending"`
3. **Current step**: `currentStep` field (UNDERSTAND, ANALYZE, IMPLEMENT, VERIFY, CONCLUDE)
4. **Previous failures**: `failureHistory` array — check for patterns

Display resume summary:
```markdown
## Resuming Feature: {featureId}
- Plan: {planPath}
- Started: {startedAtUtc}
- Last updated: {updatedAtUtc}
- Tasks completed: {N}/{total}
- Resume from: {TASK-ID} ({description})
- Previous failures: {count}
- Stop reason: {stopReason or "session ended"}
```

### Step 4: Resume Execution

1. If a task has `status: "in-progress"` — it was interrupted mid-execution:
   - **Do NOT assume previous work was persisted** — re-read all files the task touches to verify actual state
   - If the task's changes are partially applied, complete them
   - If nothing was applied, restart the task from scratch

2. If all remaining tasks are `status: "pending"` — resume normally from the next pending task

3. Continue with the same flow as `/implement-feature` Step 3 onwards:
   - IMPLEMENT remaining tasks (one at a time, updating state)
   - VERIFY (lint -> unit test -> E2E)
   - CONCLUDE (code review -> summary -> state cleanup)

### Step 5: Carry Forward Failure History

When resuming after a previous failure:
1. Check `failureHistory` for the failing task's error signatures
2. If the same task failed before with the same signature, **try a different fix approach** — don't repeat what already failed
3. If the previous `stopReason` was `"duplicate failure detected"`, report the previous blocker and ask the user for guidance before retrying

### Safety Rules

1. **Never reset completed tasks** unless the plan file changed incompatibly
2. If the plan file was modified since `updatedAtUtc`:
   - Compare task IDs — if tasks were added/removed/reordered, report the diff and ask the user whether to re-plan or adapt
   - If only descriptions changed, continue with updated descriptions
3. **Preserve all previous failure history** for debugging continuity
4. **Update `updatedAtUtc`** on every state write

$input

# Pre-PR

Pre-PR Agent: reviews code, analyzes regression risk, updates documentation, merges main, squashes commits, pushes, and creates a PR via GitHub.

## Usage

```
/pre-pr [--skip-review] [--no-push]
```

Options:
- `--skip-review`: Skip code review (if already done by Developer Agent)
- `--no-push`: Stop after squash commit, don't push or create PR

## Instructions

### Step 1: Check Review Status

Determine if `pre-pr-code-review` was already run (e.g., by the Developer Agent in the same session):

- If review results exist in the conversation context -> use those results, skip to Step 2
- If `--skip-review` flag is set -> skip review
- Otherwise -> run `/pre-pr-code-review` now

### Step 2: Regression Analysis

Analyze the git diff against `main` to identify affected flows:

```powershell
git diff origin/main...HEAD --stat
git diff origin/main...HEAD --name-only
```

For each changed file, trace its usage:
1. **Routers**: Which endpoints are affected?
2. **Processors/Services**: Which features use this service?
3. **Database methods**: Which services call this database method?
4. **Clients**: Which services use this OpenAI client method?
5. **Models/Schemas**: Which routers/services use this Pydantic model?

**Output** a regression risk report:

```markdown
## Regression Risk Analysis

### Changed Components
- `SearchProcessor.search_for_seat` — single-seat search flow
- `CVDatabase.upsert_candidate_doc` — candidate document persistence

### At-Risk Flows
1. **Single-seat search** (directly modified) — HIGH
   - Lexical retrieval, LLM verdict ranking
2. **Project search** (indirectly affected via SearchProcessor) — MEDIUM
   - Multi-seat search iterates search_for_seat

### Recommendation
- Test search endpoints via E2E or manually before merging
- Project search uses the same processor — medium risk
```

Do NOT run extra tests — just analyze the code flow.

### Step 3: Documentation

Check if structural changes warrant a doc update:

1. Look at the diff for:
   - New routers or endpoints
   - New services or client methods
   - New CLI commands
   - Changes to dependency injection or middleware pipeline
   - New database tables or columns

2. If structural changes exist:
   - Update `CLAUDE.md` with concise descriptions of new components
   - Only document new layers, components, or integrations
   - Be concise — no verbose descriptions

3. If no structural changes -> skip this step

### Step 4: Merge main

```powershell
git fetch origin
git merge origin/main
```

If conflicts:
- Report the conflicting files to the user
- Do NOT auto-resolve — ask the user for guidance
- Stop the pre-pr flow until conflicts are resolved

### Step 5: Squash Commits

Determine the merge base with main:
```powershell
git merge-base origin/main HEAD
```

Squash all feature commits into one:
```powershell
git reset --soft {merge-base-commit}
```

Then create a single commit. Extract a ticket prefix from the branch name if present (e.g., `feature/TICKET-123/description` -> `TICKET-123`). If no ticket prefix, use just the description.

```powershell
git commit -m "{description}"
```

The description should be a concise summary of all changes (from the regression analysis).

### Step 6: Commit Docs Separately

If documentation was updated in Step 3:
```powershell
git add CLAUDE.md AGENTS.md
git commit -m "docs: update project documentation"
```

### Step 7: Show Summary

Display to the user:

```markdown
## Pre-PR Summary

### Files Changed: {count}
### Code Review
{review results from Step 1 — or "Skipped"}

### Regression Risk
{risk report from Step 2}

### Documentation
{changes from Step 3 — or "No structural changes"}

### Commits
1. `{description}` ({N} files changed)
2. `docs: update project documentation` (if applicable)

Ready to push and create PR?
```

### Step 8: Confirm with User

Ask the user: **"Ready to push and create PR?"**

If `--no-push` flag is set, stop here and display the summary.

### Step 9: Push

```powershell
git push -u origin {branch-name} --force-with-lease
```

Use `--force-with-lease` because we squashed commits.

### Step 10: Create PR via GitHub

Create the PR using the `gh` CLI:

```powershell
gh pr create --title "{description}" --body "$(cat <<'EOF'
## Summary
{concise bullet points of changes}

## Regression Risk
{risk summary from Step 2}

## Verification
{test/E2E results if available}

## Code Review
{review summary if available}
EOF
)" --base main
```

Return the PR link to the user.

### Step 11: Report

```markdown
## Pre-PR Complete

- PR: {link}
- Title: {title}
- Target: main
- Files changed: {count}
- Review issues: {count or "none"}
- Regression risk: {HIGH/MEDIUM/LOW areas}
```

$input

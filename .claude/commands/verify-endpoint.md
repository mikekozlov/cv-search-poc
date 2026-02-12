# Verify Endpoint

Standalone E2E verification for any API endpoint. Runs the full server lifecycle, calls the endpoint, and verifies the response.

## Usage

```
/verify-endpoint {METHOD} {PATH}
```

Example: `/verify-endpoint POST /api/v1/search/seat`

## Instructions

### Step 1: Parse Endpoint Details

Extract from the argument: `$input`
- HTTP method (GET, POST, PUT, DELETE)
- Endpoint path (e.g., `/api/v1/search/seat`)

### Step 2: Trace Dependencies

Find the router for this endpoint:
1. Search for the route in `src/cv_search/api/` using Grep for the path pattern
2. Read the router function to identify:
   - Processor/service dependencies (e.g., `SearchProcessor`, `Planner`)
   - Database dependencies (reads/writes)
   - OpenAI client dependencies

### Step 3: Classify Verification Profile

Based on the dependency analysis:

```
Does the endpoint route through SearchProcessor/Planner (which call OpenAI)?
  NO  -> Does the endpoint write to the database?
    NO  -> e2e-light (server + call + verify response)
    YES -> e2e-mutation-internal (server + call + verify response + verify DB)
  YES -> Does the endpoint write to the database?
    NO  -> e2e-full (server + call + verify response, USE_OPENAI_STUB=1)
    YES -> e2e-mutation (server + call + verify response + verify DB, USE_OPENAI_STUB=1)
```

### Step 4: Gather Test Data

Use `mcp__db-cv-search__query` to find suitable test records:
- Find a candidate that has tags, experience, and a doc entry
- Note the IDs for use in the endpoint call

If no suitable test data exists, report to the user and suggest what data is needed.

### Step 5: Ask User for Configuration

Before starting the E2E loop, confirm with the user:
1. What is the expected response shape?
2. API key value (if `API_KEY` is set and not already known)

### Step 6: Run E2E Verification

Use the `e2e-api-test` skill to execute the full verification loop:
1. Lint check
2. Start API server (with `USE_OPENAI_STUB=1` if profile requires it)
3. Call the endpoint
4. Verify response
5. Verify database state (if mutation profile)
6. Cleanup
7. Return findings

### Step 7: Report Results

Report the verification results using the format defined in the `e2e-api-test` skill.

## Quick Reference: Common Endpoints

| Endpoint | Profile | Env Setup |
|----------|---------|-----------|
| `GET /health` | e2e-light | None |
| `GET /ready` | e2e-light | None |
| `POST /api/v1/search/seat` | e2e-mutation | `USE_OPENAI_STUB=1` |
| `POST /api/v1/search/project` | e2e-mutation | `USE_OPENAI_STUB=1` |
| `POST /api/v1/search/presale` | e2e-mutation | `USE_OPENAI_STUB=1` |
| `POST /api/v1/planner/parse-brief` | e2e-full | `USE_OPENAI_STUB=1` |
| `POST /api/v1/planner/derive-seats` | e2e-full | `USE_OPENAI_STUB=1` |
| `POST /api/v1/planner/presale-plan` | e2e-full | `USE_OPENAI_STUB=1` |
| `GET /api/v1/runs/` | e2e-light | None |
| `GET /api/v1/runs/{run_id}` | e2e-light | None |
| `POST /api/v1/runs/{run_id}/feedback` | e2e-mutation-internal | None |

$input

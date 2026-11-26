When to use: Validate code before merging — syntax, imports, call-site impact, and CI's results for tests, types and linting

# /autobot-dev-skills:review pre-merge-validate — Pre-Merge Validation Gates

## Usage
```
/autobot-dev-skills:review pre-merge-validate <PR-number>     # resolve branch via gh pr view
/autobot-dev-skills:review pre-merge-validate issue-<branch>  # use branch name directly
/autobot-dev-skills:review pre-merge-validate                 # validate current branch vs main
```

## Gates

**Setup**
1. Resolve branch: `gh pr view <number> --json headRefName -q '.headRefName'`
2. Fetch and verify: `git fetch origin main && git rev-parse origin/main origin/$BRANCH`

**Gate 0 — Squash-Duplicate Detection**
3. Count total vs truly-new commits:
   ```bash
   TOTAL=$(git log origin/main...$BRANCH --oneline | wc -l)
   NEW=$(git log --cherry-pick --right-only origin/main...$BRANCH --oneline | wc -l)
   ```
   - Block if `NEW -eq 0` (all already merged — close the PR)
   - Warn if `DUPES -gt 0 && NEW -gt 0` (partial duplicate — don't block)

**Gate 1 — Syntax + Imports (read from CI)**
4. Read CI for the head: `gh pr checks <pr>` (coordinator lanes plus suite)
   - Block on any failed syntax, import or collection check; no local compile (see `lifecycle/references/session-lifecycle.md`)

**Gate 2 — Call-Site Impact Analysis**
8. Find removed symbols:
   ```bash
   git diff origin/main...$BRANCH -- '*.py' | grep '^-def \|^-    def \|^-class ' | sed 's/^-//;s/(.*//;s/^[[:space:]]*//' | sort -u
   ```
9. Per symbol — find callers outside changed files:
   ```bash
   grep -r "$symbol" autobot-backend/ autobot-shared/ --include="*.py" --exclude-dir="tests" -l | grep -v "$(git diff --name-only ...)"
   ```
   - Block if any callers found
10. For changed signatures — compare old vs new `def $symbol(` line; block if unchanged callers exist

**Gate 3 — Targeted Test Coverage (CI is the test gate; no local test runs)**
11. Map `autobot-backend/services/kb_service.py` → `autobot-backend/tests/test_kb_service.py`
12. Check that a matching test file exists and that its CI check passed: `gh pr checks <pr>`
    - Block on a failed CI test check; Skip if no matching test files found

**Gate 4 — Types and Lint (read from CI)**
5. Read the type-check and lint checks from the same `gh pr checks <pr>` output
   - Block on a failed backend lint or type check; frontend lint failures are reported only

## Verdict
```bash
# Print gate summary table, then:
[ "$VERDICT" = "BLOCKED" ] && exit 1 || exit 0
# CLEAR TO MERGE  or  BLOCKED — fix failures before merging
```

## Integration with /team-implement
17. In SUCCESS path before `gh pr create`:
    ```bash
    /autobot-dev-skills:review pre-merge-validate issue-$issue || { mark RETRY_QUEUED, Last Failure=VALIDATION_FAILED; return; }
    ```

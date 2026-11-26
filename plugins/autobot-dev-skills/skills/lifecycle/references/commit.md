When to use: Committing in AutoBot-AI. The generic commit workflow (pre-flight, format, retry, verify) lives in `/claude-dev-skills:coding commit`; this reference holds only what is AutoBot-specific.

# AutoBot commit specifics

Run `/claude-dev-skills:coding commit` for the workflow, then apply these project rules.

- Never commit on `release` or `main`; branch names are `issue-*` or `hotfix-*` and the pre-commit hook blocks the rest.
- Message format: `<type>(scope): <description> (#issue-number)`; types `feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `perf`.
- No `Co-Authored-By` or tool trailers; `mrveiss` is the sole author.
- `git commit` never skips hooks: no hook-bypass flag on any commit. A PostToolUse hook auto-formats `.py`; re-stage with `git add -u` and commit again when a hook reformats.
- Stage explicit files for the current issue; never `git add .`.

## Common hook failures and fixes

| Hook | Symptom | Fix |
|------|---------|-----|
| black | "reformatted X.py" | `git add -u` and retry |
| isort | "Imports are incorrectly sorted" | `isort --profile=black <file> && git add <file>` |
| flake8 | "E501 line too long" | Shorten the line, `git add <file>` |
| autoflake | removed unused import | Accept it, `git add -u` |
| warn-untracked-files | untracked source files detected | Run `git diff --cached --name-only`, verify staged files belong on this branch |

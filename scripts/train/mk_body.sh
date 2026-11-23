#!/bin/bash
# Usage: mk_body.sh OUT "THINKING" "SHAPE" "sha:pr" ...
out=$1; think=$2; shape=$3; shift 3
{
  printf '## Thinking Path\n%s This merge train is built on current `main`.\n\n## What Changed\n| Member | Frozen head | Title |\n|---|---|---|\n' "$think"
  for x in "$@"; do
    h=${x%:*}; p=${x#*:}
    t=$(gh pr view "$p" --repo mrveiss/AutoBot-AI --json title -q .title)
    printf '| #%s | %s | %s |\n' "$p" "$h" "$t"
  done
  printf '\n## Why this shape\n%s\n\n## Verification\n- The listed repo guards were run on the merged tree; no full suite was run. CI is the check.\n- Not run locally: stylelint, vue-tsc, generated types.\n- None of the frontend changes has been seen in a browser.\n\n## Model Used\nClaude Opus 5.5\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n' "$shape"
} > "$out"

#!/usr/bin/env bash
# commit-subject-format.sh — reject a malformed commit subject before git sees it.
#
# PreToolUse(Bash). The convention is <type>(scope): <description> (#issue).
# CI enforces it at the PR issue-link gate, which is one push and one suite too
# late; this says the same thing at the moment the commit is written.
# Mirrors the regex in scripts/pr-preflight.sh so CI cannot be the first to say no.
# Silent no-op outside AutoBot-AI, and whenever the subject cannot be parsed.
set -uo pipefail

payload=$(cat)
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[[ "$cmd" == *"git commit"* ]] || exit 0

git config --get remote.origin.url 2>/dev/null | grep -q 'AutoBot-AI' || exit 0

# Forms that carry no inline subject to check, or reuse an existing one.
if grep -qE -- '--(amend|no-edit|fixup|squash|allow-empty-message)|(^|[[:space:]])-[FC]([[:space:]]|=)' <<<"$cmd"; then
  exit 0
fi

subject=$(SUBJ_CMD="$cmd" python3 - <<'PY'
import os, shlex, sys
try:
    tokens = shlex.split(os.environ["SUBJ_CMD"])
except ValueError:
    sys.exit(0)
for i, tok in enumerate(tokens):
    if tok == "-m" and i + 1 < len(tokens):
        print(tokens[i + 1].splitlines()[0] if tokens[i + 1] else "")
        break
    if tok.startswith("-m") and len(tok) > 2:
        print(tok[2:].splitlines()[0])
        break
PY
)

[[ -n "$subject" ]] || exit 0

if ! grep -qE '^[a-z]+(\([a-z0-9._-]+\))?: .+ \(#[0-9]+\)$' <<<"$subject"; then
  echo "BLOCKED: commit subject must match <type>(scope): <description> (#issue)"
  echo "  got: $subject"
  echo "  e.g. fix(llc): scope the goal ancestry walk (#15930)"
  exit 2
fi
if (( ${#subject} > 100 )); then
  echo "BLOCKED: commit subject is ${#subject} chars; keep it under 100"
  exit 2
fi
exit 0

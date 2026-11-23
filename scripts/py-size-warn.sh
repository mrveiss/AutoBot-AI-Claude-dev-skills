#!/usr/bin/env bash
# py-size-warn.sh — warn when a Python file crosses its size ratchet.
#
# PostToolUse(Edit|Write). The ratchet fails in CI; this reports at edit time,
# while the file is still the one being worked on.
# Ceiling = the file's entry in scripts/python_file_size_known_large.py, else
# MAX_LINES (600). Read statically; nothing from the checkout is executed.
set -uo pipefail

f=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
[[ "$f" == *.py && -f "$f" ]] || exit 0

root=$(git -C "$(dirname "$f")" rev-parse --show-toplevel 2>/dev/null) || exit 0
git -C "$root" config --get remote.origin.url 2>/dev/null | grep -q 'AutoBot-AI' || exit 0

guard="$root/scripts/check_python_file_size.py"
data="$root/scripts/python_file_size_known_large.py"
rel="${f#"$root"/}"

# Mirror the guard's own EXCLUDED_PREFIXES, read from it rather than restated,
# so a change there cannot leave this warning flagging out-of-scope files.
if [[ -f "$guard" ]]; then
  while read -r prefix; do
    [[ -n "$prefix" && "$rel" == "$prefix"* ]] && exit 0
  done < <(sed -n '/^EXCLUDED_PREFIXES = (/,/^)/p' "$guard" | grep -oE '"[^"]+"' | tr -d '"')
fi
ceiling=600
if [[ -f "$data" ]]; then
  recorded=$(grep -oE "\"${rel//\//\\/}\":[[:space:]]*[0-9]+" "$data" | grep -oE '[0-9]+$' | head -1)
  [[ -n "$recorded" ]] && ceiling="$recorded"
fi

n=$(wc -l < "$f" | tr -d ' ')
(( n > ceiling )) || exit 0

jq -nc --arg m "$rel is $n lines, over its ceiling of $ceiling — the file-size ratchet will fail CI. Split it; never raise the ceiling." \
  '{systemMessage: $m, hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $m}}'
exit 0

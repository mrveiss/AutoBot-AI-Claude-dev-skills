#!/bin/bash
# dup_precheck.sh WORKTREE — run the duplication-guard gates exactly as CI does, read at runtime
# from the worktree's own .github/workflows/duplication-guard.yml (no hand-copied flags, no drift).
# Exit 0 = every scope within its pin; non-zero = over a pin (the failing step is printed).
W=$1; cd "$W" || exit 2
PY=~/.venv-python-suite/bin/python
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
"$PY" - "$T" <<'EOF' || exit 2
import sys, yaml, pathlib
out = pathlib.Path(sys.argv[1])
wf = yaml.safe_load(open(".github/workflows/duplication-guard.yml", encoding="utf-8"))
job = wf["jobs"]["duplication-guard"]
env = {**(wf.get("env") or {}), **(job.get("env") or {})}
(out / "env.sh").write_text("".join(f"export {k}={str(v)!r}\n" for k, v in env.items()), encoding="utf-8")
n = 0
for s in job["steps"]:
    name, run = s.get("name", ""), s.get("run")
    if not run:
        continue
    if "failure" in str(s.get("if", "")):
        continue
    if name == "Load the pins" or "jscpd" in run:
        n += 1
        (out / f"{n:02d}.sh").write_text(f"# {name}\n{run}", encoding="utf-8")
print(f"extracted {n} steps", file=sys.stderr)
EOF
export GITHUB_ENV="$T/github_env"; : > "$GITHUB_ENV"
source "$T/env.sh"
rc=0
for f in "$T"/[0-9]*.sh; do
  name=$(head -1 "$f" | sed 's/^# //')
  # Private log paths (no cross-train collision) and the suite interpreter for the gate script.
  sed -i "s#/tmp/#$T/#g; s#python3 #$PY #g" "$f"
  set -a; [ -s "$GITHUB_ENV" ] && source "$GITHUB_ENV"; set +a
  [ -n "${DUP_PIN_OVERRIDE:-}" ] && export "$DUP_PIN_OVERRIDE"  # control only: e.g. SLM_MAX_DUP_LINES=1690
  if ! bash -e -o pipefail "$f" > "$T/out.log" 2>&1; then
    echo "DUP-OVER: $name"; grep -E 'clone|dup|lines|pin|exceed|over' "$T/out.log" | tail -4 | cut -c1-200; rc=1
  else
    echo "dup ok: $name"
  fi
done
exit $rc

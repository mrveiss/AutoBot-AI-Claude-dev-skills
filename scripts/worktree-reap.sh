#!/usr/bin/env bash
# worktree-reap.sh — retire worktrees whose work is safely on the remote.
#
# A worktree is a WORKSPACE, not a record. It is recreatable in seconds with
# `git worktree add <path> <branch>`. The branch is the record: durable, on the
# remote, linked to an issue. So there is no such thing as a worktree worth
# parking — parking one keeps a directory idling against the ceiling to hold
# something the remote already holds better.
#
# That makes the disposal question simpler than PR state. It is not "did this
# land?" but "would anything be lost?":
#
#   clean + fully pushed + unoccupied  ->  nothing to lose, reap it
#   dirty                              ->  commit first, then it is reapable
#   commits not on origin              ->  push first, then it is reapable
#
# A blocked tree is therefore never a refusal, it is an instruction — and the
# instruction is the same discipline that keeps work from sitting: finish a
# thing, commit it, push it. The remote branch survives the directory.
#
#   status    classify every worktree, change nothing (default)
#   reap      remove the ones that would lose nothing
#
# NEVER JUDGE "LANDED" BY ANCESTRY. `git branch --merged` and
# `git rev-list base..branch` both lie under squash-merge: squashing writes a
# new commit, so a branch's own commits never become ancestors of base and it
# reads as "76 commits ahead" forever. Nothing here uses ancestry against base.
# PR state is reported as context only, queried per branch — a bulk
# `gh pr list --state merged --limit N` truncates silently and misfiles older
# merges as never-had-a-PR, which is a confident classification of a population
# the query never saw.
#
# Gates, any one of which means report and skip:
#   1. clean          — uncommitted changes are unsaved work
#   2. pushed         — local commits absent from origin are unsaved work
#   3. no operation   — mid-merge/rebase/bisect is a live edit
#   4. unoccupied     — no process cwd inside; a session may be sitting there
#   5. not the base   — the main tree and the PR base branch are never candidates
#   6. no --force     — a tree that refuses to go is information, not an obstacle
#
# A pushed branch with no issue link is safe but forgettable, so it is held back
# unless REAP_UNLINKED=1. Findability is the point of linking work to an issue.

set -uo pipefail

MODE="${1:-status}"
REPO="${REAP_REPO:-}"
REAP_UNLINKED="${REAP_UNLINKED:-0}"
IDLE_HOURS="${REAP_IDLE_HOURS:-4}"
ESCALATE_HOURS="${REAP_ESCALATE_HOURS:-72}"

if [ -z "$REPO" ]; then REPO="$(git rev-parse --show-toplevel 2>/dev/null || true)"; fi
[ -n "$REPO" ] || { echo "worktree-reap: not in a git repo and REAP_REPO unset" >&2; exit 2; }
cd "$REPO" 2>/dev/null || { echo "worktree-reap: cannot enter $REPO" >&2; exit 2; }

BASE="${REAP_BASE:-}"
if [ -z "$BASE" ]; then
  for cand in develop main master Dev_new_gui; do
    git show-ref --verify --quiet "refs/remotes/origin/$cand" && { BASE="$cand"; break; }
  done
fi
MAIN_TREE="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's/\/\.git$//')"

occupied() {
  local path="$1" link
  for cwd in /proc/[0-9]*/cwd; do
    link="$(readlink "$cwd" 2>/dev/null)" || continue
    case "$link" in "$path"|"$path"/*) return 0 ;; esac
  done
  return 1
}

# Dirty in which direction? A file that differs from HEAD but MATCHES base has
# been put back to base content — the signature of a stray `git checkout <base> --
# .` or `git restore --source=<base>` run in a worktree instead of a scratch copy,
# which silently overwrites the branch's work. New work never looks like this.
# Distinguishing the two costs two git calls rather than hashing every file.
#
# Recovery, when it is an accident: `git restore --source=origin/<branch> -- <paths>`.
# NEVER `git stash` — the stash stack is shared across every worktree in the repo,
# so stashing here can be popped by another session.
# Hours since anything happened here. Clean-and-pushed is true between every
# commit of an active session, so cleanliness alone cannot tell "finished" from
# "mid-task" — only elapsed quiet can. Sampled from git's own metadata before any
# command in this script runs against the worktree, and every read here passes
# --no-optional-locks so the reaper never refreshes the index and resets the
# clock it is about to read.
# Unsaved work that has gone quiet is the case this tool cannot fix and must not
# hide. The reaper is a garbage collector, and a worktree holding uncommitted or
# unpushed work is not garbage — so it is skipped, reported, and skipped again on
# the next run, forever. That silence is exactly how a tree reaches 26 days and
# 44 modified files. Past ESCALATE_HOURS it stops being a log line and becomes a
# tracked issue that someone can pick up.
#
# It never commits, pushes or edits the tree. Guessing that a half-finished edit
# is worth preserving as a commit is the owner's call, not a cron's.
#
# Deduped on a marker in the body, so an hourly cron files once and comments
# never. Nothing internal goes into the issue: no absolute paths, no hostname.
# Never reap a worktree another session is still using: its branch has an open PR, or the ledger
# holds an active claim on the branch or the worktree (owner decision 2026-09-14). When the PR
# lookup itself fails, keep it: an unreachable GitHub must never mean "safe to remove".
SLUG="$(git -C "$REPO" remote get-url origin 2>/dev/null | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"
protected() {
  local branch="$1" path="$2" lg="${LEDGER_BIN:-$HOME/.claude/scripts/ledger}" out k n
  if [ -x "$lg" ]; then
    for k in "branch $branch" "worktree $(basename "$path")" "worktree $path"; do
      out="$("$lg" --as reaper who $k 2>/dev/null)"
      case "$out" in ""|*": unclaimed") ;; *)
        orphan_state "$path" 0 >/dev/null && continue  # #19452: a dead owner's claim no longer protects
        echo "ledger claim: ${out%% since*}"; return 0 ;; esac
    done
  fi
  n="$(gh pr list -R "$SLUG" --head "$branch" --state open --json number -q '.[0].number' 2>/dev/null)" \
    || { echo "open-PR lookup failed, kept to be safe"; return 0; }
  [ -n "$n" ] && { echo "open PR #$n"; return 0; }
  return 1
}

# #19452 (owner 2026-10-25: orphan recovery is automatic). A claim protects a tree only while
# its owner is alive: sessions beat on every tool use (ledger beat), so a claim heartbeat older
# than ORPHAN_HOURS means the owner stopped. An unclaimed tree idle that long is orphaned too.
ORPHAN_HOURS="${ORPHAN_HOURS:-6}"
ORPHAN_DIR="${ORPHAN_DIR:-$HOME/.claude/state/orphans}"
# Prints "<owner> <age-hours>" for an orphaned tree; returns 1 when the tree is not orphaned.
orphan_state() {
  local path="$1" idle_h="$2" lg="${LEDGER_BIN:-$HOME/.claude/scripts/ledger}" out owner ts age
  out="$("$lg" --as reaper heartbeat worktree "$(basename "$path")" 2>/dev/null)" || return 1
  if [ "$out" = "unclaimed" ]; then
    [ "$idle_h" -ge "$ORPHAN_HOURS" ] && { echo "- $idle_h"; return 0; }
    return 1
  fi
  read -r owner ts <<< "$out"
  age=$(( ( $(date +%s) - ${ts%.*} ) / 3600 ))
  [ "$age" -ge "$ORPHAN_HOURS" ] && { echo "$owner $age"; return 0; }
  return 1
}

# Read-only snapshot of an orphaned tree's unsaved work under $HOME, verified and deduplicated.
# Never commits, pushes, resets or removes anything: taking over the work is a session's call.
snapshot_orphan() {
  local path="$1" branch="$2" owner="$3" name sig dir untracked base
  name="$(basename "$path")"
  untracked="$(git -C "$path" --no-optional-locks ls-files --others --exclude-standard)"
  sig="$( { git -C "$path" rev-parse HEAD; git -C "$path" --no-optional-locks diff HEAD --binary; printf '%s\n' "$untracked"; } | sha256sum | cut -c1-16)"
  grep -rqs "^sig=$sig$" "$ORPHAN_DIR"/"$name"-*/meta.txt && { echo "$(dirname "$(grep -rls "^sig=$sig$" "$ORPHAN_DIR"/"$name"-*/meta.txt | head -1)")"; return 0; }
  dir="$ORPHAN_DIR/$name-$(date +%Y%m%d-%H%M)"; mkdir -p "$dir" || return 1
  git -C "$path" --no-optional-locks diff HEAD --binary > "$dir/diff.patch"
  [ -n "$untracked" ] && (cd "$path" && printf '%s\n' "$untracked" | tar -cf "$dir/untracked.tar" -T -)
  base="refs/remotes/origin/$branch"; git rev-parse --verify --quiet "$base" >/dev/null || base="refs/remotes/origin/$BASE"
  if [ -n "$(git -C "$path" rev-list "$base..HEAD" 2>/dev/null | head -1)" ]; then
    git -C "$path" bundle create "$dir/unpushed.bundle" "$base..HEAD" >/dev/null 2>&1 \
      && git -C "$path" bundle verify "$dir/unpushed.bundle" >/dev/null 2>&1 || { echo "bundle failed" >&2; return 1; }
  fi
  [ -n "$untracked" ] && { tar -tf "$dir/untracked.tar" >/dev/null 2>&1 || return 1; }
  printf 'sig=%s\nbranch=%s\nhead=%s\nowner=%s\ntaken=%s\n' "$sig" "$branch" "$(git -C "$path" rev-parse HEAD)" "$owner" "$(date -Is)" > "$dir/meta.txt"
  "${LEDGER_BIN:-$HOME/.claude/scripts/ledger}" --as reaper orphan worktree "$name" --owner "$owner" --snapshot "$dir" >/dev/null 2>&1
  echo "$dir"
}

escalate() {
  local branch="$1" idle_h="$2" dirty="$3" unpushed="$4" path="$5"
  local marker="worktree-stranded: $branch" existing days
  command -v gh >/dev/null 2>&1 || return 0
  existing="$(gh issue list --state open --search "\"$marker\" in:body" --limit 1 --json number -q '.[0].number' 2>/dev/null)"
  [ -n "$existing" ] && { printf ' (tracked in #%s)' "$existing"; return 0; }

  days=$(( idle_h / 24 ))
  local issue_ref="" prov
  case "$branch" in
    issue-*|hotfix-*) issue_ref="$(printf '%s' "$branch" | grep -oE '[0-9]+' | head -1)" ;;
  esac
  # host= and any absolute path are stripped: outward artifacts carry nothing internal.
  prov="$("$HOME/.claude/scripts/worktree-claim.sh" show "$path" 2>/dev/null | grep -v '^host=' | sed 's#/[^ ]*/\.worktrees/#.worktrees/#g')"

  local body
  body="$(cat <<EOF
A worktree has held unsaved work for $days days with no activity. It is not
reapable and never will be on its own: the reaper only retires work that is
safe on the remote, so this is skipped on every run and would otherwise stay
invisible indefinitely.

**This is not a request to delete anything.** The work may be worth finishing,
and nothing here has judged that. It is filed so it stops being invisible.

| | |
|---|---|
| branch | \`$branch\` |
| idle | $days days |
| uncommitted files | $dirty |
| unpushed commits | $unpushed |

## Provenance

\`\`\`
$prov
\`\`\`

A worktree goes quiet for reasons that leave no trace either way, so this is
work to resume rather than a decision someone deferred. Do not infer intent from
the silence.

## What to do

1. Recreate or enter the workspace: \`git worktree add .worktrees/$branch $branch\`
2. Review the uncommitted changes before anything else — they exist in one place only
3. Commit and push what is worth keeping; the branch is the record, the workspace is not
4. Once the branch is pushed, the reaper retires the workspace on its own

$( [ -n "$issue_ref" ] && printf 'Refs #%s\n' "$issue_ref" )

<!-- $marker -->
EOF
)"
  local new
  new="$(gh issue create --title "Stranded worktree: $branch has held unsaved work for $days days" \
        --label "tech-debt" --body "$body" 2>/dev/null | grep -oE '[0-9]+$')"
  [ -n "$new" ] && printf ' (escalated as #%s)' "$new"
}

idle_hours() {
  local path="$1" gitdir="$2" newest=0 ts
  for f in "$gitdir/index" "$gitdir/HEAD"; do
    ts="$(stat -c %Y "$f" 2>/dev/null || echo 0)"
    [ "$ts" -gt "$newest" ] && newest="$ts"
  done
  ts="$(git -C "$path" --no-optional-locks log -1 --format=%ct 2>/dev/null || echo 0)"
  [ "${ts:-0}" -gt "$newest" ] && newest="$ts"
  [ "$newest" -eq 0 ] && { printf '0'; return; }
  printf '%s' $(( ( $(date +%s) - newest ) / 3600 ))
}

# How much of a dirty tree is actually work. `git status --porcelain | wc -l`
# counts paths that differ in ANY way, and presenting that as "unsaved work" was
# wrong on all three trees this tool first escalated: one held 43 mode-bit changes
# with zero content, one held 88 untracked files that were the checkout showing
# through a one-file test-fixture tree, and the third held 44 changed paths of
# which exactly one had content. Mode bits and fixture artefacts are not work, and
# an alarm that counts them cries wolf until nobody reads it.
#
# Prints: "<content> <untracked> <modeonly>".
work_breakdown() {
  local path="$1" content untracked total_mod modeonly
  # wc -l, not grep -c: `grep -c` prints 0 AND exits 1 on no match, so a
  # `|| echo 0` fallback appends a second value and silently corrupts the fields.
  # `diff HEAD`, not bare `diff`: bare `diff` reports only UNSTAGED changes, so a
  # tree whose work is `git add`-ed measured as content=0 and was classified
  # "NOISE -- not work". Reproduced on issue-17324-coverage-pin: 2 staged paths,
  # 146 diff lines, `git diff --name-only` printed nothing. A reaper that cannot
  # see staged work is one classifier change away from deleting it.
  content="$(git -C "$path" --no-optional-locks diff HEAD --numstat 2>/dev/null | awk '$1+$2>0' | wc -l)"
  untracked="$(git -C "$path" --no-optional-locks status --porcelain 2>/dev/null | grep '^??' | wc -l)"
  total_mod="$(git -C "$path" --no-optional-locks diff HEAD --name-only 2>/dev/null | wc -l)"
  modeonly=$(( total_mod - content ))
  [ "$modeonly" -lt 0 ] && modeonly=0
  printf '%s %s %s' "$content" "$untracked" "$modeonly"
}

dirty_reason() {
  local path="$1" vs_head vs_base reverted
  vs_head="$(git -C "$path" --no-optional-locks diff --name-only HEAD 2>/dev/null | sort)"
  vs_base="$(git -C "$path" --no-optional-locks diff --name-only "refs/remotes/origin/$BASE" 2>/dev/null | sort)"
  if [ -n "$vs_head" ] && [ -n "$BASE" ]; then
    # Name-level candidates only: working differs from HEAD and matches base.
    # That set alone is not evidence — `git diff --name-only` also reports
    # mode-only changes, whose content is identical everywhere, and files the
    # branch never touched (HEAD blob == base blob), where "reverted" is
    # meaningless. Confirm against blob shas that the branch really did change
    # the file before calling it a revert.
    reverted=0
    while IFS= read -r f; do
      [ -n "$f" ] || continue
      hb="$(git -C "$path" rev-parse "HEAD:$f" 2>/dev/null)" || continue
      bb="$(git -C "$path" rev-parse "refs/remotes/origin/$BASE:$f" 2>/dev/null)" || continue
      [ "$hb" != "$bb" ] && reverted=$((reverted + 1))
    done < <(comm -23 <(printf '%s\n' "$vs_head") <(printf '%s\n' "$vs_base"))
    if [ "${reverted:-0}" -gt 0 ]; then
      printf 'REVERTED TOWARD BASE in %s file(s) — likely a stray checkout, not new work; restore with git restore --source=origin/%s' "$reverted" "$branch"
      return
    fi
  fi
  printf 'uncommitted changes — commit, then it is reapable (may be another session mid-edit)'
}

busy_operation() {
  local gitdir="$1"
  for m in MERGE_HEAD REBASE_HEAD CHERRY_PICK_HEAD BISECT_LOG REVERT_HEAD rebase-merge rebase-apply; do
    [ -e "$gitdir/$m" ] && return 0
  done
  return 1
}

# Remove one worktree and report the real outcome (#17862). A failed remove is
# printed with git's own reason and counted as `refused`, never as removed.
try_remove() {
  local path="$1" branch="$2" why="$3" err
  if err="$(git worktree remove "$path" 2>&1)"; then
    # -d refuses a squash-merged branch: ancestry cannot see the merge. The
    # remote branch is the record and it is fully pushed, so the local ref is a
    # cache and -D loses nothing.
    git branch -D "$branch" >/dev/null 2>&1 || true
    printf '%-9s %-38s %s\n' "REMOVED" "$branch" "workspace removed — $why"
    removed=$((removed + 1))
  else
    printf '%-9s %-38s %s\n' "REFUSED" "$branch" "git worktree remove failed, left intact: ${err:-no reason given}"
    refused=$((refused + 1))
  fi
}

# Linked when the branch names an issue, or when any PR exists for it.
issue_link() {
  local branch="$1"
  [[ "$branch" =~ ^(issue|hotfix)-([0-9]+) ]] && { printf 'issue #%s' "${BASH_REMATCH[2]}"; return 0; }
  local pr; pr="$(gh pr list --head "$branch" --state all --limit 5 --json number -q '.[0].number' 2>/dev/null)"
  [ -n "$pr" ] && { printf 'PR #%s' "$pr"; return 0; }
  return 1
}

# #17862: one counter per fact. `removed` counts only a `git worktree remove`
# that succeeded; a verdict with no removal behind it is `reapable`, and a
# removal that was attempted and failed is `refused` -- never folded together.
removed=0; reapable=0; refused=0; kept=0; blocked=0
if [ "$MODE" = "reap" ]; then
  echo "mode: reap -- REAPABLE worktrees are removed; each row states its outcome"
else
  echo "mode: $MODE -- classify only, NOTHING is removed (run with 'reap' to remove)"
fi
printf '%-9s %-38s %s\n' "VERDICT" "BRANCH" "REASON"
printf '%-9s %-38s %s\n' "-------" "------" "------"

while IFS= read -r path; do
  [ -n "$path" ] || continue
  [ "$path" = "$MAIN_TREE" ] && continue
  branch="$(git -C "$path" branch --show-current 2>/dev/null || true)"
  gitdir="$(git -C "$path" rev-parse --absolute-git-dir 2>/dev/null || true)"

  if [ -z "$branch" ]; then
    printf '%-9s %-38s %s\n' "KEEP" "(detached)" "no branch — nowhere to push, verify by hand"
    kept=$((kept + 1)); continue
  fi
  if [ "$branch" = "$BASE" ]; then
    printf '%-9s %-38s %s\n' "KEEP" "$branch" "the PR base — never a candidate"
    kept=$((kept + 1)); continue
  fi

  idle="$(idle_hours "$path" "$gitdir")"
  if [ -n "$(git -C "$path" --no-optional-locks status --porcelain 2>/dev/null)" ]; then
    read -r wb_content wb_untracked wb_mode <<< "$(work_breakdown "$path")"
    if [ "$wb_content" -eq 0 ] && [ "$wb_untracked" -eq 0 ]; then
      printf '%-9s %-38s %s\n' "NOISE" "$branch" "$wb_mode mode-bit change(s), zero content — not work, not escalated"
      blocked=$((blocked + 1)); continue
    fi
    printf '%-9s %-38s %s' "COMMIT" "$branch" \
      "$wb_content file(s) with content, $wb_untracked untracked, $wb_mode mode-only — commit what is work"
    if [ "$MODE" = "reap" ] && orphan="$(orphan_state "$path" "$idle")"; then
      snap="$(snapshot_orphan "$path" "$branch" "${orphan%% *}")" && printf ' (orphaned: snapshot %s)' "${snap/#$HOME/~}"
    fi
    if [ "$MODE" = "reap" ] && [ "$idle" -ge "$ESCALATE_HOURS" ]; then
      escalate "$branch" "$idle" "$wb_content" \
               "$(git -C "$path" --no-optional-locks rev-list --count '@{upstream}..HEAD' --not "refs/remotes/origin/$BASE" 2>/dev/null || echo 0)" "$path"
    fi
    printf '\n'
    blocked=$((blocked + 1)); continue
  fi
  if [ -n "$gitdir" ] && busy_operation "$gitdir"; then
    printf '%-9s %-38s %s\n' "KEEP" "$branch" "git operation in progress"
    blocked=$((blocked + 1)); continue
  fi

  # --verify --quiet is required: a bare `rev-parse <missing-ref>` echoes the ref
  # name back on stdout and fails, so `|| true` captures the literal string and a
  # missing remote branch reads as a valid sha.
  if ! git rev-parse --verify --quiet "refs/remotes/origin/$branch" >/dev/null 2>&1; then
    # A missing remote branch has two opposite meanings and they must not be
    # conflated: either the work was never pushed (push it, the branch is the
    # record), or it MERGED and the branch was deleted afterwards — in which
    # case origin/main already holds every commit and the tree is free to go.
    # Reading both as "push it" is why this reaper retired 0 of 11 workspaces
    # on 2026-09-20 while the worktree ceiling blocked three sessions from
    # diagnosing their own CI failures. Non-merge commits only: the auto-update
    # bot's merges of main carry no content of this branch's own.
    unlanded=$(git log --oneline --no-merges "origin/main..$branch" 2>/dev/null | wc -l)
    if [ "${unlanded:-1}" -ne 0 ]; then
      printf '%-9s %-38s %s\n' "PUSH" "$branch" "no remote branch, $unlanded unlanded commit(s) — push it, the branch is the record"
      blocked=$((blocked + 1)); continue
    fi
    printf '%-9s %-38s %s\n' "LANDED" "$branch" "remote branch gone and every commit is in origin/main — merged, reapable"
    landed_no_remote=1
  else
    landed_no_remote=
  fi
  # Only "ahead" is unsaved work. Behind is stale, not lost: origin holds every
  # commit this tree does, so the workspace is still free to go.
  #
  # Skipped entirely for a LANDED branch: it has no origin/<branch> to compare
  # against, so this would read "cannot compare — failing safe" and keep a tree
  # whose work is already provably in main. That fall-through is what made the
  # check above print LANDED and then retire nothing anyway.
  if [ -z "$landed_no_remote" ]; then
    counts="$(git -C "$path" rev-list --left-right --count "refs/remotes/origin/$branch...HEAD" 2>/dev/null || true)"
    ahead="$(printf '%s' "$counts" | awk '{print $2}')"
    if [ -z "$ahead" ]; then
      printf '%-9s %-38s %s\n' "KEEP" "$branch" "cannot compare with origin — failing safe"
      blocked=$((blocked + 1)); continue
    fi
  else
    ahead=0
  fi
  # The refresh cron merges base into every clean worktree hourly, including ones
  # whose branch already landed. That leaves unpushed commits holding no original
  # work — the merge itself, plus every commit it drags in from base, including
  # the squash commit of this branch's own PR. Counting merge commits was not
  # enough: a squash commit has one parent, so base content read as original work.
  #
  # What matters is whether anything here exists ONLY here. Commits reachable from
  # base are excluded, and of what remains only a base merge carrying git's own
  # generated subject is excused.
  #
  # KNOWN LIMIT: that subject test cannot see conflict resolutions. A session that
  # ran `git merge origin/<base>` by hand and resolved conflicts produces the same
  # subject, so its resolutions would be treated as nothing original and discarded
  # with the workspace. The window is narrow — the branch must be otherwise fully
  # pushed, idle past the threshold and unoccupied — and the loss is reconstructible
  # by re-merging, but it is a real loss and not a theoretical one. Detecting it
  # properly needs the merge re-computed and compared, which is why it is recorded
  # here rather than claimed as handled.
  if [ "$ahead" -gt 0 ]; then
    original=0
    while IFS= read -r sha; do
      [ -n "$sha" ] || continue
      parents="$(git -C "$path" --no-optional-locks rev-list --parents -n1 "$sha" 2>/dev/null | wc -w)"
      subject="$(git -C "$path" --no-optional-locks log -1 --format=%s "$sha" 2>/dev/null)"
      if [ "$parents" -ge 3 ] && [ "${subject#Merge remote-tracking branch \'origin/$BASE\'}" != "$subject" ]; then
        continue
      fi
      original=$((original + 1))
    done < <(git -C "$path" --no-optional-locks rev-list "refs/remotes/origin/$branch..HEAD" --not "refs/remotes/origin/$BASE" 2>/dev/null)

    if [ "$original" -eq 0 ]; then
      printf '%-9s %-38s %s\n' "REAPABLE" "$branch" "$ahead unpushed commit(s), all from base or the refresh merge — nothing original"
      if [ "$MODE" != "reap" ]; then
        reapable=$((reapable + 1)); continue
      fi
      if [ "$idle" -lt "$IDLE_HOURS" ] || occupied "$path"; then
        printf '%-9s %-38s %s\n' "  -> KEPT" "$branch" "not removed: occupied or touched under ${IDLE_HOURS}h ago"
        kept=$((kept + 1)); continue
      fi
      if why="$(protected "$branch" "$path")"; then
        printf '%-9s %-38s %s\n' "  -> KEPT" "$branch" "not removed: in use by a session ($why)"
        kept=$((kept + 1)); continue
      fi
      try_remove "$path" "$branch" "nothing original was unpushed"
      continue
    fi
    printf '%-9s %-38s %s' "PUSH" "$branch" "$original original commit(s) not on origin — push, then it is reapable"
    if [ "$MODE" = "reap" ] && orphan="$(orphan_state "$path" "$idle")"; then
      snap="$(snapshot_orphan "$path" "$branch" "${orphan%% *}")" && printf ' (orphaned: snapshot %s)' "${snap/#$HOME/~}"
    fi
    if [ "$MODE" = "reap" ] && [ "$idle" -ge "$ESCALATE_HOURS" ]; then
      escalate "$branch" "$idle" 0 "$original" "$path"
    fi
    printf '\n'
    blocked=$((blocked + 1)); continue
  fi

  if occupied "$path"; then
    printf '%-9s %-38s %s\n' "KEEP" "$branch" "a process is sitting in it"
    kept=$((kept + 1)); continue
  fi
  if [ "$idle" -lt "$IDLE_HOURS" ]; then
    printf '%-9s %-38s %s\n' "ACTIVE" "$branch" "touched ${idle}h ago — under the ${IDLE_HOURS}h idle threshold"
    kept=$((kept + 1)); continue
  fi

  if ! link="$(issue_link "$branch")"; then
    if [ "$REAP_UNLINKED" != "1" ]; then
      printf '%-9s %-38s %s\n' "LINK" "$branch" "pushed but no issue or PR — link it so it stays findable"
      blocked=$((blocked + 1)); continue
    fi
    link="unlinked"
  fi

  if [ "$MODE" != "reap" ]; then
    printf '%-9s %-38s %s\n' "REAPABLE" "$branch" "pushed to origin, not necessarily landed ($link), idle ${idle}h — removing the workspace loses nothing"
    reapable=$((reapable + 1)); continue
  fi

  if why="$(protected "$branch" "$path")"; then
    printf '%-9s %-38s %s\n' "KEPT" "$branch" "in use by a session ($why) — not removed"
    kept=$((kept + 1)); continue
  fi
  try_remove "$path" "$branch" "work lives on origin ($link)"
done < <(git worktree list --porcelain | awk '/^worktree /{print substr($0, 10)}')

echo
echo "removed: $removed   reapable, not removed: $reapable   refused: $refused   kept: $kept   needs action: $blocked"
if [ "$MODE" != "reap" ] && [ "$reapable" -gt 0 ]; then
  echo "nothing was removed: this was a '$MODE' pass. Run 'worktree-reap.sh reap' to remove the $reapable REAPABLE worktree(s)."
elif [ "$MODE" = "reap" ] && [ "$removed" -eq 0 ] && [ $((refused + reapable)) -gt 0 ]; then
  echo "nothing was removed: every REAPABLE row above says why (REFUSED = git refused; KEPT = protected, occupied or recent)."
fi
[ "$removed" -gt 0 ] && echo "resume any removed branch with: git worktree add .worktrees/<name> <branch>"
exit 0

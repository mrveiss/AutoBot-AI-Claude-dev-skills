# Session Lifecycle Protocol

Sessions are mortal: they terminate before their PRs merge, so a session can
never clean up after its own merge. This protocol inverts responsibility —
**every session cleans up after its predecessors at start, and leaves a
`.notes/` handoff at end.**

Base branch: `main` (adjust if the dispatch says otherwise).

## SESSION START (do this before any task work)

1. **Sync, and REPORT — do not sweep:**
   ```bash
   git fetch --prune
   git worktree prune          # safe: only drops admin refs whose dir is already gone
   git worktree list           # read-only inventory
   ```

   **A worktree may be retired automatically, and that is not a lost session.**
   An hourly reaper removes any workspace that is clean, fully pushed, unoccupied
   and idle past a threshold — including ones you did not create. Nothing is lost
   when it does: the branch is the record and the workspace is recreatable with
   `git worktree add .worktrees/<name> <branch>`. A worktree holding uncommitted
   or unpushed work is never reaped, and past 72h idle it is escalated to a
   tracked issue instead. So the way to keep your work is to push it, not to keep
   the directory.

   **Never delete a worktree or branch you did not create.** Other sessions run
   concurrently, and a worktree that is clean with zero commits ahead is
   indistinguishable from a finished one — it is usually a session that has just
   started. A prior version of this step force-removed anything that looked
   merged and destroyed an in-progress worktree mid-task.

   Exceptions, and only these two: the user asks, or the leftover belongs to the
   issue you were dispatched to work on. Otherwise list what you found in the
   report and move on.

   When an exception applies, **cleanup means finishing the work, not deleting it**
   — see `~/.claude/docs/worktrees.md`:
   - **Landed** (the branch's own work is solved and merged, verified in base)
     → dispose, even if an umbrella issue is still open. A worktree is cheap to
     recreate; unfinished work is not.
   - **Stale** (untouched for several days, not landed) → rebase onto base →
     link or file its issue → solve it → PR → review → merge → *then* dispose.
   - **Active** (touched recently, or zero commits — a session that just
     started) → leave alone.
   - never `--force` (a dirty tree refusing removal is unfinished work, not an obstacle)
   - `git branch -D` only after the branch's PR is verified merged — never on
     ancestry alone
   - skip anything `locked`

2. **Create YOUR isolated worktree**, then claim it so a concurrent sweep cannot
   take it (never work in a shared checkout; never two sessions in one directory):
   ```bash
   # from the main checkout's root; <name> is issue-<n> when there is an issue
   git worktree add .worktrees/<name> -b <name> origin/main
   ledger iam <session>
   ledger claim worktree <name> --ttl 168h
   ```
   `ledger` lives in the user's Claude scripts directory, which must be on `PATH`.
   The ledger is the ownership record (`ledger who worktree <name>`); no claim
   commit. Address the worktree by path (`git -C`), never through an earlier `cd`.
   On removal: `ledger release worktree <name>`, then `git worktree remove`.
3. **Read `.notes/INDEX.md` if present** (gitignored in-repo handoff; AutoBot:
   `docs/developer/SESSION_END.md`) and pick up the open notes it lists. If a
   note's branch is unmerged, continue it (rebase onto base first) or start
   fresh — never duplicate its work blind.
4. **No local test runs** — CI and merge trains are the gate. Run only the
   targeted lint/guards for the files you touch.

## DURING THE SESSION

- One commit per logical change; reference issues (`fixes #NNNN`).
- LICENSE, NOTICE, SPDX headers, and licensing statements are READ-ONLY.
  Flag concerns in the report; never modify.
- Never push directly to the base branch. Never merge yourself — Hand off to the trainmaster's merge train — see `pr` Step 5.
- If you discover another session has landed overlapping work: rebase onto
  latest base immediately and reconcile before continuing.

## SESSION END (mandatory before terminating — also run when blocked)

1. **Leave nothing uncommitted:** `git status` must be clean. Work-in-progress
   that can't be completed gets committed to your branch with a `wip:` prefix
   and explained in its `.notes/` topic note — never left dangling in the worktree.
2. **Rebase onto latest base:**
   ```bash
   git fetch origin && git rebase origin/main
   ```
   If the rebase conflicts and resolution is non-trivial, STOP — resolve only
   what you are confident about; otherwise note the conflict precisely in the
   topic note for the next session. NEVER commit conflict markers (grep
   `^<<<<<<< ` across the tree before the final push).
3. **Push and open/update the PR** with `gh pr create` (or `gh pr edit`):
   title = mission, body = summary + link to the report.
4. **Follow AutoBot `docs/developer/SESSION_END.md`:**
   - **Notes:** `.notes/` is the only handoff — branch state, CI status and next
     steps go in the topic note or on the branch's issue/PR. Write/update `.notes/yyyy.mm.dd-topic.md` per open topic and list
     each in `.notes/INDEX.md` (file, topic, issue, next step). Delete notes whose
     work is complete (move anything still needed into code, `docs/` or an issue
     first); delete `INDEX.md` when no notes remain.
   - **Issues:** file every parked, deferred, unapproved or blocked item (search
     duplicates first); post decisions on the matching issue; close only when
     verifiably done.
   - **Memory:** save new owner preferences and long-lived facts.
   - **Scratch:** remove temp files and caches not belonging on the branch.
   - **Push everything** — no local-only work; report anything uncommitted.
   - **Remove every worktree** you hold: `ledger release worktree <name>`, then
     `git worktree remove .worktrees/<name>` (no `--force`; a dirty tree refusing
     removal is unfinished work — push or commit it first).
   - **Deployed copy (optional):** update to latest `main` via the builtin updater
     only; if it cannot be done now, file an issue.
5. **Write the mission report** (`*_REPORT.md` per the dispatch prompt) — for the human. Point it
   at `.notes/INDEX.md` and the issues.

## FAILURE MODES THIS PREVENTS
- Orphaned branches drifting behind base (start-step 1 + end-step 2)
- Committed conflict markers (end-step 2 grep)
- Two sessions colliding in one checkout (start-step 2)
- Duplicate work on the same problem (start-step 3 notes)
- Posthumous cleanup that never happens (inheritance model)
- Silent license/business-model changes (during-session read-only rule)

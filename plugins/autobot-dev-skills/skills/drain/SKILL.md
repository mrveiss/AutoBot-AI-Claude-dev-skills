---
name: drain
description: Pick and solve the backlog issues that need no decision. Use when asked to work the backlog, drain issues, "solve what you can", run the loop autonomously, or whenever a loop tick has no assigned issue. Selects work; delegates execution to batch-implement.
---

# /drain — spend the loop's attention on what it can actually finish

The loop's scarce resource is **attention**, not filing capacity. Picking the
oldest open issue blindly burns a tick whenever it turns out to need an answer
only the owner can give. This selects work that is finishable now.

Selection only. Execution belongs to `batch-implement`; PR mechanics to
`ci-pipelining.md`. Do not reimplement either here.

## 1. Land what is already finished, before starting anything

Two queues hold finished work, and the open-PR list is only the visible one.
Work that never reached a PR is invisible to `gh pr list` and is the larger pile:
measured at 120 commits on 22 branches, 83 of them on branches with no PR ever
opened, against 1-2 open PRs at the time.

```bash
gh pr list --state open --json number,title --jq '.[]|"\(.number) \(.title)"'
~/.claude/scripts/drain-parked.sh                # branches whose commits never landed
~/.claude/scripts/worktree-cap.sh status         # headroom before a new worktree is refused
~/.claude/scripts/backlog-governor.sh status     # advisory signal only
```

Sweep → review → merge green → close with evidence → remove worktree/branch.
A merged PR closes an issue; a new issue closes nothing.

**If either queue is non-empty, draining it IS the tick.** Land the top row of
`drain-parked.sh` before selecting new work — it is the cheapest already-paid-for
work still returning nothing. A worktree ceiling of zero headroom means this step
is not optional: the next `git worktree add` is refused until something lands.

## 2. Select

```bash
~/.claude/scripts/backlog-next.py -n 10 --why
```

Ranks problems → enhancements → features, FIFO within each. Judged from issue
content, not labels — labels do not carry this signal (1 of 400 open issues
carries `needs-decision`). An issue is excluded when it is an umbrella, requests
a decision, has an open `depends on #N` blocker, or states no acceptance
criteria.

Take the head of the list that does not collide with an in-flight PR's files.
Skipping for collision is a deferral, not a reorder.

## 3. Confirm readiness before starting

The picker is a heuristic. Read the issue and abandon it if:

- the acceptance criteria are not actually checkable
- it needs a product or architecture call
- delivering it means choosing between two reasonable designs

Put it back with a `needs-decision` label and options + a recommendation posted
on the issue, then take the next candidate **in the same tick**. Never end a
tick because one issue turned out to be decision-gated.

## 4. Execute

Hand the chosen numbers to `batch-implement`, which owns worktree → implement →
review → merge → close → cleanup.

## Hard rules

- **Never file issues as busywork.** Filing is never blocked, but a filed issue
  is not progress. If nothing is solvable, say so and stop — do not manufacture
  backlog to look busy.
- **Discovered problems still get filed** (that rule is absolute), just never as
  a substitute for solving something.
- **A decision-gated issue is posted and skipped, never waited on.**
- **Evidence before done** — `batch-implement` and the closure gate own this;
  do not claim a close without the verifying output.

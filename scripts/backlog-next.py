#!/usr/bin/env python3
"""backlog-next — rank the open issues a loop can finish WITHOUT a decision.

The loop's scarce resource is attention, not filing capacity. Picking the
oldest problem blindly burns a tick whenever that issue turns out to need an
answer only the owner can give. This ranks what is actually finishable now.

    backlog-next.py [-n N] [--json] [--why]

Readiness is judged from issue CONTENT, not labels: on this repo only 1 of 400
open issues carries `needs-decision`, so labels cannot carry the signal.

An issue is READY when all of:
  * it states acceptance criteria (spec'd enough that "done" is checkable) --
    in the body OR in any comment, since criteria are often agreed after filing
  * it is not an umbrella (umbrellas coordinate; their children implement)
  * it does not request a decision (options/recommendation awaiting an owner)
  * every `depends on #N` blocker it names is already closed

Ranking follows the loop's existing order: problems -> enhancements ->
features, then FIFO by issue number so old work is never overtaken.

Repo is derived from the working directory; nothing here is machine-specific.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

BLOCKER = re.compile(r"depends on #(\d+)", re.I)
ACCEPTANCE = re.compile(r"acceptance criteria", re.I)
UMBRELLA = re.compile(r"\bumbrella\b|\bepic\b", re.I)
DECISION = re.compile(
    r"decision needed|needs a decision|needs-decision|owner picks|"
    r"^\s*##+\s*options\b|which (do you|would you) (want|prefer)",
    re.I | re.M,
)
PROBLEM = re.compile(
    r"\b(fix|bug|regression|security|broken|unwired|leak|crash|race|"
    r"dead code|tech debt|stub|no-?op|silently)\b",
    re.I,
)
FEATURE = re.compile(r"^\s*(feat|feature)\b|\badd support\b|\bnew capability\b", re.I)


def gh_json(*args: str) -> list[dict]:
    out = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        sys.exit(f"gh failed: {out.stderr.strip()}")
    return json.loads(out.stdout or "[]")


def kind(issue: dict) -> str:
    """problem -> enhancement -> feature, matching the loop's ordering rule."""
    hay = f"{issue['title']} {' '.join(l['name'] for l in issue.get('labels', []))}"
    if PROBLEM.search(hay):
        return "problem"
    if FEATURE.search(issue["title"]):
        return "feature"
    return "enhancement"


def blockers(body: str, open_numbers: set[int]) -> list[int]:
    """Only blockers that are still OPEN actually block."""
    return sorted({int(n) for n in BLOCKER.findall(body or "") if int(n) in open_numbers})


def discussion(issue: dict) -> str:
    """Body plus every comment.

    The decisive context is routinely in the comments, not the body: acceptance
    criteria added after filing, a blocker discovered later, a decision raised
    in review. Reading only the body picks up issues whose comments say "this
    needs an owner call", and skips issues whose criteria were agreed in a
    follow-up. Both directions were observed on this repo (#15299 session).
    """
    parts = [issue.get("body") or ""]
    parts += [(c.get("body") or "") for c in issue.get("comments", [])]
    return "\n".join(parts)


def assess(issue: dict, open_numbers: set[int]) -> tuple[bool, str]:
    body = discussion(issue)
    labels = {l["name"].lower() for l in issue.get("labels", [])}

    if labels & {"needs-decision", "blocked", "question", "wontfix", "on-hold"}:
        return False, f"labelled {', '.join(sorted(labels & {'needs-decision','blocked','question','wontfix','on-hold'}))}"
    if UMBRELLA.search(issue["title"]):
        return False, "umbrella — coordinates children, does not implement"
    if DECISION.search(body):
        return False, "requests a decision from the owner"
    open_blockers = blockers(body, open_numbers)
    if open_blockers:
        return False, "blocked by " + ", ".join(f"#{n}" for n in open_blockers)
    if not ACCEPTANCE.search(body):
        return False, "no acceptance criteria — 'done' is not checkable"
    return True, "ready"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10, help="how many to show (default 10)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--why", action="store_true", help="also list what was excluded, and why")
    args = ap.parse_args()

    issues = gh_json(
        "issue", "list", "--state", "open", "--limit", "600",
        "--json", "number,title,body,labels,comments",
    )
    open_numbers = {i["number"] for i in issues}

    ready, skipped = [], []
    for i in issues:
        ok, why = assess(i, open_numbers)
        row = {"number": i["number"], "title": i["title"], "kind": kind(i), "why": why}
        (ready if ok else skipped).append(row)

    order = {"problem": 0, "enhancement": 1, "feature": 2}
    ready.sort(key=lambda r: (order[r["kind"]], r["number"]))

    if args.json:
        print(json.dumps({"ready": ready[: args.n], "skipped": len(skipped)}, indent=2))
        return 0

    print(f"{len(ready)} of {len(issues)} open issues are finishable without a decision\n")
    for r in ready[: args.n]:
        print(f"  [{r['kind'][:4]}] #{r['number']}  {r['title'][:78]}")

    if args.why:
        reasons: dict[str, int] = {}
        for s in skipped:
            key = re.sub(r"#\d+", "#N", s["why"])
            reasons[key] = reasons.get(key, 0) + 1
        print("\n  excluded:")
        for why, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"    {n:4d}  {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

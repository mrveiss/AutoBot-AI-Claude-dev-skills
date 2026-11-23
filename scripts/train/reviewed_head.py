"""Exit 0 when a PR's head is its last approved head, or differs only by clean merges of main."""
import json
import os
import re
import subprocess
import sys

R = "mrveiss/AutoBot-AI"
G = os.environ.get("AUTOBOT_REPO") or os.path.expanduser("~/AutoBot-Ai/AutoBot-AI")


def git(*a):
    return subprocess.run(["git", "-C", G, *a], capture_output=True, text=True).stdout


def floor_only(commit, combined):
    """Whether a commit or a merge's resolution changes only reach floors (a look a script can give)."""
    out = git("show", "--format=", "--cc" if combined else "-p", commit)
    lines = [l for l in out.splitlines() if l[:2].strip("+- ") == "" and l[:2] != "  " and l[:1] in "+-" or (combined and l[:2] in ("++", "--", "+ ", "- ", " +", " -"))]
    changed = [l for l in lines if not l.startswith(("+++", "---"))]
    return all("floor=" in l or "mid-window" in l for l in changed)


def main(pr, head=None):
    d = json.loads(subprocess.run(["gh", "pr", "view", pr, "-R", R, "--json", "comments,headRefOid"], capture_output=True, text=True).stdout)
    head = head or d["headRefOid"]
    subprocess.run(["git", "-C", G, "fetch", "-q", "origin", "main", f"pull/{pr}/head"], capture_output=True)
    last = None
    for c in d["comments"]:
        m = re.search(r"Code review on PR #\d+ \(head ([0-9a-f]{7,40})\): \*\*([^*]+)\*\*", c["body"])
        if m:
            last = (m.group(1), m.group(2).strip().lower())
    if not last:
        print(f"{pr} NO-REVIEW {head[:10]}")
        return 1
    sha, verdict = last
    if not verdict.startswith("approve"):
        print(f"{pr} NOT-APPROVED {sha[:10]} {verdict}")
        return 1
    full = git("rev-parse", "--verify", "-q", sha + "^{commit}").strip()
    if not full:
        print(f"{pr} UNKNOWN-REVIEWED-SHA {sha[:10]}")
        return 1
    new = git("rev-list", f"{full}..{head}", "^origin/main").split()
    for c in new:
        parents = git("rev-list", "--parents", "-n1", c).split()[1:]
        synced = len(parents) == 2 and not git("rev-list", parents[1], "^origin/main").strip()
        if synced and floor_only(c, True):
            continue
        if len(parents) == 1 and floor_only(c, False):
            continue
        if True:
            print(f"{pr} FRESH-LOOK {sha[:10]}..{head[:10]} at {c[:10]}")
            return 1
    print(f"{pr} OK reviewed={sha[:10]} head={head[:10]} sync_merges={len(new)}")
    return 0


sys.exit(main(*sys.argv[1:3]))

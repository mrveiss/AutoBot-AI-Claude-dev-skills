"""Oldest approved PRs clear to board, packed to a file budget. Prints candidates and blockers."""
import json, subprocess, sys
R = "mrveiss/AutoBot-AI"
HOLD = {20427, 20464, 20561, 19456, 20550, 20536, 20538, 20581, 20294, 20566, 20563, 19621, 20222, 20251, 20418, 20420, 20461, 20477, 20481, 20486, 20494, 20495, 20502, 20515, 20530}
BUDGET = int(sys.argv[1]) if len(sys.argv) > 1 else 90
d = json.loads(subprocess.run(["gh", "pr", "list", "-R", R, "--state", "open", "--limit", "200", "--json", "number,headRefName,isDraft,mergeable,changedFiles"], capture_output=True, text=True).stdout)
T = '{repository(owner:"mrveiss",name:"AutoBot-AI"){pullRequest(number:%d){reviewThreads(first:60){nodes{isResolved}}}}}'
total, take, skip = 0, [], []
for p in sorted(d, key=lambda x: x["number"]):
    n = p["number"]
    if p["headRefName"].startswith("train-") or p["isDraft"] or n in HOLD:
        continue
    if p["mergeable"] != "MERGEABLE":
        skip.append(f"{n}:{p['mergeable'].lower()}"); continue
    r = subprocess.run(["python3", sys.argv[2], str(n)], capture_output=True, text=True)
    if r.returncode:
        skip.append(f"{n}:{r.stdout.split()[1] if r.stdout.split()[1:] else 'x'}"); continue
    t = json.loads(subprocess.run(["gh", "api", "graphql", "-f", "query=" + T % n], capture_output=True, text=True).stdout)
    if any(not x["isResolved"] for x in t["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]):
        skip.append(f"{n}:threads"); continue
    if total + p["changedFiles"] > BUDGET:
        skip.append(f"{n}:budget({p['changedFiles']})"); continue
    total += p["changedFiles"]; take.append(n)
print("take", total, *take); print("skip", *skip)

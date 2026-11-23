"""Three-way merge of a commit onto origin/main in a temporary index; print what the merge would change."""
import os, subprocess, sys, tempfile
def git(*a, env=None, ok=True):
    r = subprocess.run(["git", *a], capture_output=True, env=env)
    if ok and r.returncode: raise SystemExit(f"git {a[0]} rc={r.returncode}: {r.stderr[:200]!r}")
    return r
def blob(sha, path):
    with open(path, "wb") as f: f.write(git("cat-file", "blob", sha).stdout)
def check(head):
    main = git("rev-parse", "origin/main").stdout.decode().strip()
    bases = git("merge-base", "--all", main, head).stdout.decode().split()
    if not bases: return None
    base = bases[0]
    with tempfile.TemporaryDirectory() as d:
        env = {**os.environ, "GIT_INDEX_FILE": os.path.join(d, "idx")}
        git("read-tree", "-i", "-m", "--aggressive", base, main, head, env=env)
        unm = {}
        for l in git("ls-files", "-u", "-z", env=env).stdout.decode(errors="replace").split("\0"):
            if l:
                m, s, st, p = l.replace("\t", " ", 1).split(" ", 3); unm.setdefault(p, {})[st] = s
        adds, conflicts = [], []
        for p, e in unm.items():
            if not {"1", "2", "3"} <= set(e): conflicts.append(p); continue
            if e["2"] == e["3"]: continue
            a, o, b = [os.path.join(d, x) for x in "aob"]
            blob(e["2"], a); blob(e["1"], o); blob(e["3"], b)
            r = subprocess.run(["git", "merge-file", "-p", a, o, b], capture_output=True)
            if r.returncode: conflicts.append(p)
            elif r.stdout != open(a, "rb").read(): adds.append(p)
        resolved = git("diff-index", "--cached", "--name-only", main, "--", env=env).stdout.decode().split()
        adds += [p for p in resolved if p not in unm]
    return len(bases), adds, conflicts
for h in sys.argv[1:]:
    r = check(h)
    print(h[:40], "NOBASE" if r is None else f"bases={r[0]} adds={len(r[1])} conflicts={len(r[2])} " + " ".join((r[1] + r[2])[:4]))

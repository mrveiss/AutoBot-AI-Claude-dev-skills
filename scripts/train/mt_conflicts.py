"""Usage: mt_conflicts.py A B — print files that conflict when merging B into A (git 2.34 three-arg merge-tree)."""
import subprocess, sys
a, b = sys.argv[1], sys.argv[2]
base = subprocess.run(["git", "merge-base", a, b], capture_output=True, text=True).stdout.strip()
out = subprocess.run(["git", "merge-tree", base, a, b], capture_output=True, text=True, errors="replace").stdout
conf, path, sect = set(), None, None
for ln in out.split("\n"):
    if ln and not ln[0].isspace() and not ln.startswith(("@@", "+", "-")):
        sect, path = ln.strip(), None
        continue
    if ln.startswith("  ") and sect and len(ln.split()) >= 4 and path is None:
        path = ln.split()[-1]
    if path and ln.startswith("+<<<<<<<"):
        conf.add(path)
    if sect in ("added in both",) and path and ln.startswith("+<<<<<<<"):
        conf.add(path)
print(" ".join(sorted(conf)))

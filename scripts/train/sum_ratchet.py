"""Resolve a conflict in the i18n ratchet: both sides raised per-locale counts, so sum the increases."""
import re, subprocess
P = "repo_tests/i18n_untranslated_ratchet_test.py"
s = open(P, encoding="utf-8").read()
base = subprocess.run(["git", "show", ":1:" + P], capture_output=True, text=True).stdout
LINE = re.compile(r'^(\s+)"(\w+)": (\d+)(,.*)$', re.M)
b = {m.group(2): int(m.group(3)) for m in LINE.finditer(base)}
def fix(m):
    ours = {x.group(2): x for x in LINE.finditer(m.group(1))}
    theirs = {x.group(2): x for x in LINE.finditer(m.group(2))}
    out = []
    for k, t in theirs.items():
        o = ours[k]
        n = int(o.group(3)) + int(t.group(3)) - b[k]
        out.append(f'{t.group(1)}"{k}": {n}{t.group(4)}\n')
    return "".join(out)
s, n = re.subn(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", fix, s, flags=re.S)
assert n, "no conflict"
open(P, "w", encoding="utf-8").write(s)
print("resolved", n)

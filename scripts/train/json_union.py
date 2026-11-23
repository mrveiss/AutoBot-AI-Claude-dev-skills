#!/usr/bin/env python3
"""3-way JSON union for a conflicted file: json_union.py [--sets] <path> <base-ref> <ours-ref> <theirs-ref>.
Keeps ours' key order, appends theirs' new keys; a leaf both sides changed differently is a hard error.
--sets: string lists are SETS -- keep an entry only if neither side removed it, add both sides' additions;
a key removed by either side is dropped; output is indent 2 and the file must exist in all three refs."""
import json, subprocess, sys
SETS = "--sets" in sys.argv
path, base, ours, theirs = [a for a in sys.argv[1:] if a != "--sets"][:4]
def load(ref):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else {}
def merge(b, o, t, where):
    if isinstance(o, dict) and isinstance(t, dict):
        b = b if isinstance(b, dict) else {}
        out = {}
        for k in list(o) + [k for k in t if k not in o]:
            if k in o and k in t: out[k] = merge(b.get(k), o[k], t[k], f"{where}.{k}")
            elif k in o: 
                if k in b and k not in t and o[k] == b[k]: continue  # theirs deleted, ours unchanged
                out[k] = o[k]
            else:
                if k in b and k not in o and t[k] == b[k]: continue  # ours deleted, theirs unchanged
                out[k] = t[k]
        return out
    if o == t: return o
    if o == b: return t
    if t == b: return o
    sys.exit(f"CONFLICT at {where}: ours={o!r} theirs={t!r}")
def set_load(ref): return json.loads(subprocess.check_output(["git", "show", f"{ref}:{path}"]))
def set_merge(b, o, t, where):
    if isinstance(o, dict):
        out = {}
        for k in list(o) + [k for k in t if k not in o]:
            if b is not None and k in b and (k not in o or k not in t): continue
            if k not in t: out[k] = o[k]; continue
            if k not in o: out[k] = t[k]; continue
            out[k] = set_merge((b or {}).get(k), o[k], t[k], where + [k])
        return out
    if isinstance(o, list) and all(isinstance(x, str) for x in o + t):
        bl = b or []
        keep = [x for x in o if x not in bl or x in t]
        return keep + [x for x in t if x not in bl and x not in keep]
    if o == t: return o
    if o == b: return t
    if t == b: return o
    sys.exit(f"real conflict at {where}: {o!r} vs {t!r}")
if SETS:
    open(path, "w", encoding="utf-8").write(json.dumps(set_merge(set_load(base), set_load(ours), set_load(theirs), []), indent=2) + "\n")
    sys.exit(0)
res = merge(load(base), load(ours), load(theirs), path)
raw = subprocess.run(["git", "show", f"{ours}:{path}"], capture_output=True, text=True).stdout
indent = 4 if '\n    "' in raw[:300] and '\n  "' not in raw[:300] else 2
open(path, "w", encoding="utf-8").write(json.dumps(res, indent=indent, ensure_ascii=False) + "\n")
print("merged", path)

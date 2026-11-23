"""Re-pin the bare cast guard's named floor mid-window when stale; repin_reach_floors.py skips a named constant."""
import re, sys
from pathlib import Path
sys.path.insert(0, ".")
import repo_tests.env_var_bare_cast_test as t
root = Path(".").resolve()
if t.REACH.staleness(root) is not None:
    low, high, mid = t.REACH.window(root); c = t.REACH.population(root)
    p = Path("repo_tests/env_var_bare_cast_test.py"); s = p.read_text(encoding="utf-8")
    s, n = re.subn(r"^MIN_FILES_SCANNED = \d+  # mid-window:[^\n]*", f"MIN_FILES_SCANNED = {mid}  # mid-window: population {c}, window [{low}, {high}] (the merge train)", s, flags=re.M)
    assert n == 1
    p.write_text(s, encoding="utf-8"); print("PIN   env-var-bare-cast named floor ->", mid)

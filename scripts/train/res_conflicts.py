"""Resolve the mechanical merge conflicts in the current tree: reach floors take ours, size lists take real counts."""
import os
import re
import subprocess
import sys

PAT = re.compile(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n", re.S)
# Per-file strategies carried over from the retired resolve.py fork.
UNION = {"repo_tests/changes_job_equivalence_15360_test.py", "repo_tests/reach_scope_claim_17844_test.py",
         "repo_tests/_reach_unscoped.py", "repo_tests/_glob_declared_uncovered.py"}  # both sides add entries: keep both
VERDS = {"repo_tests/_reach_policy_verdicts.py", "repo_tests/_reach_policy_verdicts_n_to_z.py",
         "repo_tests/_reach_policy_verdicts_a_to_m.py"}  # keep both, closing ours' entry between them
ROOTS = "repo_tests/_reach_roots_record.py"  # take ours
SIZE_LISTS = {"repo_tests/python_file_size_ratchet_baseline.py", "scripts/python_file_size_known_large.py"}


def conflicted():
    out = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True).stdout
    return [l[3:] for l in out.splitlines() if l[:2] in ("UU", "AA", "DU", "UD")], out


def sizes(m):
    lines = []
    for line in m.group(1).splitlines(True):
        k = re.match(r'\s+"([^"]+)": (\d+)', line)
        if k:
            with open(k.group(1), encoding="utf-8") as fh:
                count = sum(1 for _ in fh)
            line = line.replace(f'": {k.group(2)}', f'": {count}', 1)
        lines.append(line)
    return "".join(lines)


def sizes_if_present(m):
    out = []
    for line in m.group(1).splitlines(True):
        k = re.match(r'(\s*)"([^"]+)":\s*\d+,(.*)', line)
        if k and os.path.exists(k.group(2)):
            with open(k.group(2), encoding="utf-8") as fh:
                line = f'{k.group(1)}"{k.group(2)}": {sum(1 for _ in fh)},{k.group(3)}\n'
        out.append(line)
    return "".join(out)


def main():
    files, _ = conflicted()
    bad = []
    for path in files:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if path in UNION:
            text = PAT.sub(lambda m: m.group(1) + m.group(2), text)
        elif path in VERDS:
            text = PAT.sub(lambda m: m.group(1) + "    ),\n" + m.group(2), text)
        elif path == ROOTS:
            text = PAT.sub(lambda m: m.group(1), text)
        elif path in SIZE_LISTS:
            text = PAT.sub(sizes_if_present, text)
        elif path.endswith(("_file_size_known_large.py",)):
            text = PAT.sub(sizes, text)
        else:
            hunks = PAT.findall(text)
            if not hunks or any(
                any(not re.match(r"\s*floor=", ln) for ln in (a + b).splitlines() if ln.strip()) for a, b in hunks
            ):
                bad.append(path)
                continue
            text = PAT.sub(lambda m: m.group(1), text)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    if bad:
        print("NONMECHANICAL", *bad)
        sys.exit(1)


main()

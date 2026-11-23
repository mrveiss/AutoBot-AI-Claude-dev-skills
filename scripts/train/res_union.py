"""Registry files: both sides add entries, so keep both. Generated env docs: regenerate. Anything else stays conflicted."""
import os, re, subprocess, sys
PY = os.environ.get("AUTOBOT_PY") or os.path.join(os.environ.get("AUTOBOT_REPO") or os.path.expanduser("~/AutoBot-Ai/AutoBot-AI"), "venv/bin/python")
u = subprocess.run(["git", "diff", "--name-only", "--diff-filter=U"], capture_output=True, text=True).stdout.split()
regen = False
for f in u:
    if re.search(r"autobot_shared/env_registry_\w+\.py$", f):
        s = open(f, encoding="utf-8").read()
        s, n = re.subn(r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n",
                       lambda m: m.group(1) + "    )\n)\n\nregister_env_var(\n    EnvVarSpec(\n" + m.group(2) if m.group(1).lstrip().startswith("name=") else m.group(1) + m.group(2),
                       s, flags=re.S)
        compile(s, f, "exec")
        open(f, "w", encoding="utf-8").write(s); print("union", f, n)
    elif f == "docs/developer/ENV_VARS.md":
        subprocess.run(["git", "checkout", "--ours", "--", f], check=True); regen = True
if regen:
    r = subprocess.run([PY, "pipeline-scripts/generate_env_docs.py"], capture_output=True, text=True)
    print("regen rc", r.returncode, r.stdout[-90:].strip())
    if r.returncode: sys.exit(1)

"""Count skill invocations and context injected by attachments/hooks over 7 days (#21716 baseline)."""
import collections
import glob
import json
import os
import time

ROOT = os.path.expanduser("~/.claude/projects/" + os.environ.get("TOKEN_MEASURE_PROJECT", os.path.abspath(os.environ.get("AUTOBOT_REPO", "~/AutoBot-Ai/AutoBot-AI")).replace("/", "-")))
DAYS = int(os.environ.get("DAYS", "7"))
CUT = time.time() - DAYS * 86400


def scan(path, skills, size, count, loaded):
    pend = {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message") or {}
        c = m.get("content") if isinstance(m, dict) else None
        if d.get("type") == "assistant" and isinstance(c, list):
            for b in c:
                if b.get("type") == "tool_use" and b.get("name") == "Skill":
                    name = b["input"].get("skill")
                    skills[name] += 1
                    pend[b["id"]] = name
        if d.get("type") == "user" and d.get("isMeta") and isinstance(c, list) and d.get("sourceToolUseID") in pend:
            loaded[pend[d["sourceToolUseID"]]] += len(json.dumps(c))
        if d.get("type") == "attachment":
            a = d.get("attachment", {})
            n = a.get("hookName") or a.get("type")
            size[n] += len(json.dumps(a))
            count[n] += 1


def main():
    skills, size, count, loaded = (collections.Counter() for _ in range(4))
    for p in glob.glob(ROOT + "/*.jsonl") + glob.glob(ROOT + "/*/subagents/*.jsonl"):
        if os.path.getmtime(p) >= CUT:
            scan(p, skills, size, count, loaded)
    print(f"SKILL invocations ({DAYS}d):")
    for k, v in skills.most_common(25):
        print(f"  {k:45} {v:4}  loaded~{loaded[k]//4/1e3:.0f}k tok")
    print("ATTACHMENTS/hooks injected (~chars/4 tokens):")
    for k, v in size.most_common(15):
        print(f"  {k:45} n={count[k]:6} ~{v//4/1e6:.2f}M tok")


if __name__ == "__main__":
    main()

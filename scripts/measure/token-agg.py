"""Aggregate 7-day token usage by subagent type from Claude Code transcripts (#21716 baseline)."""
import collections
import glob
import json
import os
import time

ROOT = os.path.expanduser("~/.claude/projects/" + os.environ.get("TOKEN_MEASURE_PROJECT", os.path.abspath(os.environ.get("AUTOBOT_REPO", "~/AutoBot-Ai/AutoBot-AI")).replace("/", "-")))
DAYS = int(os.environ.get("DAYS", "7"))
CUT = time.time() - DAYS * 86400


def usage(path, c):
    seen = set()
    for line in open(path, encoding="utf-8", errors="ignore"):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") != "assistant":
            continue
        m = d.get("message", {})
        mid = m.get("id")
        if mid in seen:
            continue
        seen.add(mid)
        u = m.get("usage") or {}
        c["in"] += u.get("input_tokens", 0)
        c["cw"] += u.get("cache_creation_input_tokens", 0)
        c["cr"] += u.get("cache_read_input_tokens", 0)
        c["out"] += u.get("output_tokens", 0)
        c["calls"] += 1
        c["model:" + str(m.get("model"))] += 1


def eq(c):
    # input-price equivalents: cache write x1.25, cache read x0.1, output x5 (model price not weighted)
    return c["in"] + 1.25 * c["cw"] + 0.1 * c["cr"] + 5 * c["out"]


def main():
    agents = collections.defaultdict(collections.Counter)
    for p in glob.glob(ROOT + "/*/subagents/*.jsonl"):
        if os.path.getmtime(p) < CUT:
            continue
        try:
            meta = json.load(open(p[:-6] + ".meta.json", encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        c = agents[meta.get("agentType", "?")]
        c["n"] += 1
        usage(p, c)
    main_c = collections.Counter()
    for p in glob.glob(ROOT + "/*.jsonl"):
        if os.path.getmtime(p) >= CUT:
            usage(p, main_c)
    tot = sum(eq(c) for c in agents.values()) + eq(main_c) or 1
    print(f"MAIN calls={main_c['calls']} eqM={eq(main_c)/1e6:.0f} share={eq(main_c)/tot:.0%}")
    for k, c in sorted(agents.items(), key=lambda x: -eq(x[1])):
        mods = sorted(((k2[6:], v) for k2, v in c.items() if k2.startswith("model:")), key=lambda x: -x[1])[:2]
        print(f"{k:34} n={c['n']:4} eqM={eq(c)/1e6:7.1f} share={eq(c)/tot:5.1%} "
              f"per-run={eq(c)/c['n']/1e6:5.2f}M out={c['out']/1e6:5.1f}M {mods}")


if __name__ == "__main__":
    main()

"""Usage: lostcheck.py [--at-merge] REF RANGE
(default: own added lines are looked up in REF; --at-merge: in the merge commit itself.)
For each 'Merge #N @ sha' on a train: files its first-parent merge changed, and own files whose added lines are missing from the ref."""
import re,subprocess,sys
def g(*a): return subprocess.run(["git",*a],capture_output=True).stdout.decode("utf-8","replace")
at_merge="--at-merge" in sys.argv; args=[a for a in sys.argv[1:] if a!="--at-merge"]
ref,rng=args[0],args[1]
for l in g("log","--merges","--format=%H %s",rng).splitlines():
    sha,s=l.split(" ",1); m=re.match(r"Merge #(\d+) @ ([0-9a-f]+)",s)
    if not m: continue
    pr,h=m.groups(); fp=g("diff","--name-only",sha+"^1",sha).split()
    base=g("merge-base",sha+"^1",h).strip(); own=g("diff","--name-only",base,h).split()
    low=[]
    for f in own:
        add=[x[1:].strip() for x in g("diff","--unified=0",base,h,"--",f).splitlines() if x.startswith("+") and not x.startswith("+++")]
        add=[a for a in add if len(a)>=12 and "floor=" not in a]
        if not add: continue
        body=set(x.strip() for x in g("show",f"{sha if at_merge else ref}:{f}").splitlines())
        hit=sum(a in body for a in add)
        if hit*2<len(add): low.append(f"{f.split('/')[-1]}:{hit}/{len(add)}")
    flag="EMPTY " if not fp else ""
    print(f"{flag}#{pr} {h[:10]} merge_changed={len(fp)} own={len(own)} low_survival={len(low)} {' '.join(low[:5])}")

import json,re,subprocess,sys
def sh(*a): return subprocess.run(a,capture_output=True,text=True).stdout
Q='{repository(owner:"mrveiss",name:"AutoBot-AI"){pullRequest(number:%s){headRefOid mergeable changedFiles isDraft reviewThreads(first:60){nodes{isResolved}} comments(last:60){nodes{body}}}}}'
for p in sys.argv[1:]:
    d=json.loads(sh("gh","api","graphql","-f","query="+Q%p))["data"]["repository"]["pullRequest"]
    rev=[m for c in d["comments"]["nodes"] for m in re.findall(r"Code review on PR #\d+ \(head ([0-9a-f]+)\): \*\*approve",c["body"])]
    t=sum(not n["isResolved"] for n in d["reviewThreads"]["nodes"])
    print(p,d["headRefOid"][:10],d["mergeable"],"f=%d"%d["changedFiles"],"threads=%d"%t,"rev="+(rev[-1][:10] if rev else "-"),"DRAFT" if d["isDraft"] else "")

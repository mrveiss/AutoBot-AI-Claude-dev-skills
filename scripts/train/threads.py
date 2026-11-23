"""Print a PR's unresolved review threads with HTML and collapsed sections stripped."""
import json
import re
import subprocess
import sys

Q = '{repository(owner:"mrveiss",name:"AutoBot-AI"){pullRequest(number:%s){reviewThreads(first:60){nodes{isResolved path line comments(first:1){nodes{body}}}}}}}'
for pr in sys.argv[1:]:
    out = subprocess.run(["gh", "api", "graphql", "-f", "query=" + Q % pr], capture_output=True, text=True).stdout
    nodes = json.loads(out)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    print("==", pr)
    for n in nodes:
        if n["isResolved"]:
            continue
        b = re.sub(r"<details>.*?</details>", "", n["comments"]["nodes"][0]["body"], flags=re.S)
        b = re.sub(r"<!--.*?-->|<picture>.*?</picture>|<[^>]+>", "", b, flags=re.S)
        print(" ", f'{n["path"]}:{n["line"]}', "::", " ".join(b.split())[:300])

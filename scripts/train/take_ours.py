import re,sys
for p in sys.argv[1:]:
    s=open(p,encoding="utf-8").read()
    s,n=re.subn(r"<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> [^\n]*\n", r"\1", s, flags=re.S)
    assert "<<<<<<<" not in s, p
    open(p,"w",encoding="utf-8").write(s); print(p,n)

import json, subprocess, sys, os, time, select
p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=open(sys.argv[1]+"/appserver.err","w"), env=dict(os.environ, CODEX_HOME=sys.argv[1]+"/home"), cwd=sys.argv[1]+"/proj")
def send(m): p.stdin.write((json.dumps(m)+"\n").encode()); p.stdin.flush()
def recv(want_id, t=15):
    end=time.time()+t
    while time.time()<end:
        r,_,_=select.select([p.stdout],[],[],0.5)
        if r:
            l=p.stdout.readline()
            if not l: break
            m=json.loads(l)
            if m.get("id")==want_id: return m
            print("NOTIF", json.dumps(m)[:300])
    return None
send({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"clientInfo":{"name":"probe","version":"0"}}})
print("INIT", json.dumps(recv(1))[:300])
send({"jsonrpc":"2.0","method":"initialized","params":{}})
for i,(meth,params) in enumerate([("hooks/list",{}),("hooks/list",{"cwd":sys.argv[1]+"/proj"}),("hooks/list",{"cwds":[sys.argv[1]+"/proj"]})],start=2):
    send({"jsonrpc":"2.0","id":i,"method":meth,"params":params})
    print(meth, params, json.dumps(recv(i))[:2500])
p.terminate()

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from lsp_probe import Client
def run(root, f):
    root = Path(root).resolve(); c = Client(str(root), reply=True)
    c.request("initialize", {"processId": os.getpid(), "rootUri": root.as_uri(),
        "workspaceFolders": [{"uri": root.as_uri(), "name": "w"}],
        "capabilities": {"textDocument": {"publishDiagnostics": {}}, "workspace": {"configuration": True}}})
    c.notify("initialized", {})
    uri = Path(f).resolve().as_uri(); t0 = c.t()
    c.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "robotframework", "version": 1, "text": Path(f).read_text()}})
    first, d = c.wait_diag(uri, t0, timeout=60)
    c.request("shutdown", None, timeout=10); c.notify("exit", None)
    return first and round(first - t0, 2), [(x['severity'], x['message'][:100]) for x in (d or []) if x['severity'] == 1]
M = os.path.dirname(os.path.abspath(__file__))
print("root=projA      ", run(f"{M}/projA", f"{M}/projA/tests/shop.robot"))
print("root=parent dir ", run(M, f"{M}/projA/tests/shop.robot"))

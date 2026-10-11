"""Q3: client for STOCK `robotcode repl-server` using robotcode's own JSON-RPC classes.

usage: python jsonrpc_client.py SOCKET_PATH|PORT op [cell]      op = exec | shutdown | interrupt
"""
import asyncio
import json
import sys

from robotcode.jsonrpc2.protocol import JsonRPCProtocol


async def main(addr: str, op: str, cell: str = "") -> int:
    loop = asyncio.get_running_loop()
    if addr.isdigit():
        transport, proto = await loop.create_connection(JsonRPCProtocol, "127.0.0.1", int(addr))
    else:
        transport, proto = await loop.create_unix_connection(JsonRPCProtocol, addr)
    try:
        if op == "exec":
            res = await proto.send_request_async("executeCell", {"source": cell, "language_id": "robotframework"})
            # compact it the same way rfmcp_local does: top-level keyword nodes only
            steps = []
            for item in res.get("items") or []:
                if item["mime"] == "x-application/robotframework-repl-log":
                    root = json.loads(item["data"])
                    for n in root.get("items", []):
                        if n.get("node_type") == "keyword":
                            steps.append({"kw": n["name"], "owner": n["owner"], "status": n["status"],
                                          **({"msg": n["message"]} if n["status"] == "FAIL" else {})})
            print(json.dumps({"ok": res.get("success"), "steps": steps}))
        else:
            res = await asyncio.wait_for(proto.send_request_async(op, {}), 60)
            print(json.dumps({"ok": True, "result": res}))
    finally:
        transport.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(*sys.argv[1:])))

"""Monitor Pharos USDC Transfer logs through Chain MCP; no signing."""
import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

MCP = "https://mcp.pharos.xyz/mcp"
CONTRACT = "0xc879c018db60520f4355c26ed1a6d572cdac1815"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


def post(method, params, session=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session:
        headers["Mcp-Session-Id"] = session
    req = Request(MCP, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                   "params": params}).encode(), headers, method="POST")
    with urlopen(req, timeout=25) as response:
        body = response.read().decode()
        session = response.headers.get("Mcp-Session-Id") or session
    if body.startswith("event:"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    result = json.loads(body)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"], session


def tool(name, arguments, session):
    result, _ = post("tools/call", {"name": name, "arguments": arguments}, session)
    if result.get("isError"):
        raise RuntimeError(result["content"])
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def decode(log, decimals=6):
    topics = log["topics"]
    if len(topics) != 3 or topics[0].lower() != TRANSFER:
        raise ValueError("Unexpected event")
    amount = int(log["data"], 16)
    whole, fractional = divmod(amount, 10 ** decimals)
    readable = str(whole) + (("." + str(fractional).zfill(decimals).rstrip("0")) if fractional else "")
    return {"block": int(log["blockNumber"], 16), "tx_hash": log["transactionHash"],
            "log_index": int(log["logIndex"], 16),
            "from": "0x" + topics[1][-40:], "to": "0x" + topics[2][-40:],
            "amount": readable, "symbol": "USDC"}


def poll(session, state, max_blocks=1000):
    latest = int(tool("get_block_number", {}, session)["blockNumber"])
    start = state["next_block"]
    if start > latest:
        return []
    end = min(latest, start + max_blocks - 1)
    raw = tool("get_logs", {"address": CONTRACT, "topics": [TRANSFER],
                            "fromBlock": hex(start), "toBlock": hex(end)}, session)
    logs = raw.get("logs") if isinstance(raw, dict) else raw
    if not isinstance(logs, list):
        raise ValueError("Unexpected MCP logs response")
    unique = {(e["transactionHash"], e["logIndex"]): decode(e) for e in logs if not e.get("removed")}
    state["next_block"] = end + 1
    return sorted(unique.values(), key=lambda e: (e["block"], e["log_index"]))


def self_test():
    log = {"topics": [TRANSFER, "0x" + "0" * 24 + "1" * 40,
                      "0x" + "0" * 24 + "2" * 40], "data": hex(1234567),
           "blockNumber": "0xa", "transactionHash": "0xabc", "logIndex": "0x0"}
    assert decode(log)["amount"] == "1.234567"
    assert decode(log)["from"] == "0x" + "1" * 40
    state = {"next_block": 10}
    assert state["next_block"] < 11


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path("event-monitor-state.json"))
    parser.add_argument("--backfill", type=int, default=10, help="Blocks to check on first run")
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    if args.backfill < 1 or args.interval < 1:
        parser.error("backfill and interval must be positive")
    _, session = post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "arena-event-monitor", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")
    chain = tool("get_chain_info", {}, session)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    state = json.loads(args.state.read_text()) if args.state.exists() else {
        "next_block": max(0, int(chain["latestBlock"]) - args.backfill + 1)}
    while True:
        events = poll(session, state)
        for event in events:
            print(json.dumps(event), flush=True)
        args.state.write_text(json.dumps(state) + "\n")
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

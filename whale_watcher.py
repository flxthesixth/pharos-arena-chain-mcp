"""Read-only multi-address whale watcher backed by hosted Pharos Chain MCP."""
import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.request import Request, urlopen

MCP = "https://mcp.pharos.xyz/mcp"
TRANSFER = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def exchange(method, params, session=None, request_id=1):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session:
        headers["Mcp-Session-Id"] = session
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    with urlopen(Request(MCP, json.dumps(payload).encode(), headers, method="POST"), timeout=30) as response:
        body = response.read().decode()
        session = response.headers.get("Mcp-Session-Id") or session
    if body.startswith("event:"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    reply = json.loads(body)
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"], session


class ChainMCP:
    def __init__(self):
        _, self.session = exchange("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                                  "clientInfo": {"name": "whale-watching-agent", "version": "1.0"}})
        if not self.session:
            raise RuntimeError("Chain MCP session missing")

    def call(self, name, arguments):
        result, _ = exchange("tools/call", {"name": name, "arguments": arguments}, self.session)
        if result.get("isError"):
            raise RuntimeError(result["content"])
        return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def load_config(path):
    config = json.loads(Path(path).read_text())
    watched = config.get("watched_addresses", {})
    if len(watched) < 5:
        raise ValueError("watched_addresses must contain at least 5 addresses")
    for address in [*watched, *config.get("tokens", {}), *config.get("known_labels", {})]:
        if not ADDRESS.fullmatch(address):
            raise ValueError(f"invalid address: {address}")
    if not config.get("tokens"):
        raise ValueError("at least one token is required")
    for token in config["tokens"].values():
        if int(token["decimals"]) < 0 or Decimal(token["significant_threshold"]) < 0:
            raise ValueError("token decimals and threshold must be non-negative")
    if int(config.get("lookback_blocks", 0)) < 1:
        raise ValueError("lookback_blocks must be positive")
    return config


def address_topic(address):
    return "0x" + "0" * 24 + address[2:].lower()


def raw_logs(call, token, watched, start, end):
    """Query indexed sender/recipient separately; dedupe self-transfers."""
    found = {}
    topics = [address_topic(a) for a in watched]
    for page in range(start, end + 1, 1000):
        stop = min(page + 999, end)
        for position in (1, 2):
            query = [TRANSFER, None, None]
            query[position] = topics
            result = call("get_logs", {"address": token, "topics": query,
                                       "fromBlock": hex(page), "toBlock": hex(stop)})
            logs = result.get("logs", result) if isinstance(result, dict) else result
            if not isinstance(logs, list):
                raise ValueError("unexpected Chain MCP get_logs response")
            for log in logs:
                if not log.get("removed"):
                    found[(log["transactionHash"], log["logIndex"])] = log
    return found.values()


def amount_text(raw, decimals):
    return format(Decimal(raw) / (Decimal(10) ** decimals), "f")


def build_report(config, call, observed_at=None):
    chain = call("get_chain_info", {})
    expected = int(config["network"]["chain_id"])
    if chain.get("chainId") != expected or not chain.get("chainIdMatches"):
        raise RuntimeError(f"Chain MCP chain mismatch; expected {expected}")
    latest = int(chain.get("latestBlock", int(chain["latestBlockHex"], 16)))
    start = max(0, latest - int(config["lookback_blocks"]) + 1)
    watched = {k.lower(): v for k, v in config["watched_addresses"].items()}
    labels = {**{k.lower(): v for k, v in config.get("known_labels", {}).items()}, **watched}
    explorer = config["network"]["explorer"].rstrip("/")
    moves = []
    for token_address, token in config["tokens"].items():
        decimals = int(token["decimals"])
        threshold = Decimal(token["significant_threshold"])
        for log in raw_logs(call, token_address, watched, start, latest):
            sender = "0x" + log["topics"][1][-40:].lower()
            recipient = "0x" + log["topics"][2][-40:].lower()
            amount = Decimal(int(log["data"], 16)) / (Decimal(10) ** decimals)
            watched_parties = [a for a in (sender, recipient) if a in watched]
            moves.append({
                "block": int(log["blockNumber"], 16), "tx_hash": log["transactionHash"],
                "log_index": int(log["logIndex"], 16), "token": token["symbol"],
                "amount": format(amount, "f"), "significant": amount >= threshold,
                "threshold": format(threshold, "f"),
                "from": {"address": sender, "label": labels.get(sender, "unknown")},
                "to": {"address": recipient, "label": labels.get(recipient, "unknown")},
                "watched_addresses": watched_parties,
                "explanation": f"{format(amount, 'f')} {token['symbol']} moved from {labels.get(sender, 'unknown')} to {labels.get(recipient, 'unknown')}",
                "explorer_url": f"{explorer}/tx/{log['transactionHash']}",
            })
    moves.sort(key=lambda x: (x["block"], x["log_index"]), reverse=True)
    per_address = {}
    for address, label in watched.items():
        related = [m for m in moves if address in m["watched_addresses"]]
        sent = sum((Decimal(m["amount"]) for m in related if m["from"]["address"] == address), Decimal())
        received = sum((Decimal(m["amount"]) for m in related if m["to"]["address"] == address), Decimal())
        per_address[address] = {"label": label, "transfers": len(related), "significant_transfers": sum(m["significant"] for m in related),
                                "sent": format(sent, "f"), "received": format(received, "f"),
                                "explorer_url": f"{explorer}/address/{address}"}
    return {
        "task": "whale-watching-agent", "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
        "source": {"provider": "Pharos Chain MCP", "endpoint": MCP, "tools": ["get_chain_info", "get_logs"],
                   "read_only": True},
        "network": {"name": config["network"]["name"], "chain_id": expected,
                    "latest_block": latest, "from_block": start, "to_block": latest},
        "configuration": {"watched_address_count": len(watched), "watched_addresses": config["watched_addresses"],
                          "tokens": config["tokens"], "lookback_blocks": config["lookback_blocks"]},
        "summary": {"transfer_count": len(moves), "significant_transfer_count": sum(m["significant"] for m in moves),
                    "by_address": per_address},
        "significant_moves": [m for m in moves if m["significant"]], "recent_activity": moves,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("whale_watcher_config.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = build_report(load_config(args.config), ChainMCP().call)
    text = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()

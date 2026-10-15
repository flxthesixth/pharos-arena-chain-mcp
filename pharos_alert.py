"""Send large Pharos USDC Transfer alerts to a Discord webhook."""
import argparse
import json
import os
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request, urlopen

from arena_event_monitor import CONTRACT, TRANSFER, decode, post, tool


def save(path, cursor):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(cursor) + "\n")
    os.replace(temp, path)


def alert(event, threshold, send):
    if Decimal(event["amount"]) < threshold:
        return False
    text = (f"Pharos USDC Transfer: {event['amount']} USDC\n"
            f"From: {event['from']}\nTo: {event['to']}\n"
            f"Block: {event['block']}\n"
            f"https://www.pharosscan.xyz/tx/{event['tx_hash']}")
    send(text)
    return True


def webhook_sender(url):
    if not url.startswith("https://discord.com/api/webhooks/") and not url.startswith("https://discordapp.com/api/webhooks/"):
        raise ValueError("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook URL")
    def send(text):
        request = Request(url, json.dumps({"content": text}).encode(),
                          {"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=20) as response:
            if response.status not in (200, 204):
                raise RuntimeError(f"Discord delivery failed: HTTP {response.status}")
    return send


def process(session, cursor, state_path, threshold, send, max_blocks=100):
    latest = int(tool("get_block_number", {}, session)["blockNumber"])
    start = cursor["block"]
    if start > latest:
        return 0
    end = min(latest, start + max_blocks - 1)
    result = tool("get_logs", {"address": CONTRACT, "topics": [TRANSFER],
                               "fromBlock": hex(start), "toBlock": hex(end)}, session)
    logs = result.get("logs") if isinstance(result, dict) else result
    if not isinstance(logs, list):
        raise ValueError("Unexpected MCP logs response")
    events = sorted((decode(log) for log in logs if not log.get("removed")),
                    key=lambda item: (item["block"], item["log_index"]))
    sent = 0
    for event in events:
        if (event["block"], event["log_index"]) <= (cursor["block"], cursor["log_index"]):
            continue
        sent += alert(event, threshold, send)
        cursor.update(block=event["block"], log_index=event["log_index"])
        save(state_path, cursor)
    cursor.update(block=end + 1, log_index=-1)
    save(state_path, cursor)
    return sent


def self_test():
    e = {"amount": "100.000001", "from": "0x1", "to": "0x2", "block": 7, "tx_hash": "0xabc"}
    out = []
    assert alert(e, Decimal("100"), out.append) and len(out) == 1
    assert "https://www.pharosscan.xyz/tx/0xabc" in out[0]
    assert not alert(e, Decimal("101"), out.append) and len(out) == 1
    try:
        webhook_sender("http://localhost:8000")
    except ValueError:
        pass
    else:
        raise AssertionError("insecure webhook accepted")
    raw = {"topics": [TRANSFER, "0x" + "0" * 24 + "1" * 40,
                      "0x" + "0" * 24 + "2" * 40], "data": hex(100000001),
           "blockNumber": "0xa", "transactionHash": "0xabc", "logIndex": "0x0"}
    def fake_tool(name, arguments, session):
        return {"blockNumber": 10} if name == "get_block_number" else {"logs": [raw]}
    with TemporaryDirectory() as directory, patch(__name__ + ".tool", fake_tool):
        state_path = Path(directory) / "cursor.json"
        cursor = {"block": 10, "log_index": -1}
        assert process("test", cursor, state_path, Decimal("100"), out.append) == 1
        assert process("test", cursor, state_path, Decimal("100"), out.append) == 0
        assert len(out) == 2 and json.loads(state_path.read_text())["block"] == 11
        cursor = {"block": 10, "log_index": -1}
        def fail(text):
            raise URLError("simulated delivery failure")
        try:
            process("test", cursor, state_path, Decimal("100"), fail)
        except URLError:
            assert cursor == {"block": 10, "log_index": -1}
        else:
            raise AssertionError("failure incorrectly advanced cursor")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-usdc", required=False, default="100", help="Minimum transfer value in USDC")
    parser.add_argument("--state", type=Path, default=Path("alert-state.json"))
    parser.add_argument("--backfill", type=int, default=10)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    try:
        minimum = Decimal(args.min_usdc)
    except InvalidOperation:
        parser.error("--min-usdc must be a number")
    if not minimum.is_finite() or minimum < 0 or args.backfill < 1 or args.interval < 1:
        parser.error("threshold must be finite and nonnegative; backfill and interval must be positive")
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        parser.error("set DISCORD_WEBHOOK_URL in environment; never commit the URL")
    send = webhook_sender(webhook)
    _, session = post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "pharos-alert", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")
    chain = tool("get_chain_info", {}, session)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    cursor = json.loads(args.state.read_text()) if args.state.exists() else {
        "block": max(0, int(chain["latestBlock"]) - args.backfill + 1), "log_index": -1}
    while True:
        count = process(session, cursor, args.state, minimum, send)
        print(f"Delivered {count} alerts", flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

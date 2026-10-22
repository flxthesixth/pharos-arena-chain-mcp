"""Export a read-only Pharos wallet audit report from hosted Chain MCP data."""
import argparse
import json
import re
import time as clock
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError

from arena_contract_state import exchange, text

CHAIN_ID = 1672
EXPLORER = "https://www.pharosscan.xyz"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
CATEGORIES = ("transfers_in", "transfers_out", "swaps", "approvals", "contract_interactions")
SWAP_SELECTORS = {
    "0x38ed1739", "0x8803dbee", "0x7ff36ab5", "0x18cbafe5", "0x4a25d94a",
    "0x5c11d795", "0x414bf389", "0xdb3e2198", "0x04e45aaf", "0xb858183f",
}
ADDRESS_RE = re.compile(r"0x[0-9a-fA-F]{40}\Z")


def validate_wallet(wallet):
    if not ADDRESS_RE.fullmatch(wallet):
        raise ValueError("wallet must be 0x followed by 40 hexadecimal characters")
    return wallet.lower()


def parse_time(value, end=False):
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            day = datetime.fromisoformat(value).date()
            return datetime.combine(day + (timedelta(days=1) if end else timedelta()), time(), timezone.utc)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"invalid ISO-8601 date/time: {value}") from error
    if parsed.tzinfo is None:
        raise ValueError("date/time must include a timezone")
    return parsed.astimezone(timezone.utc)


def parse_range(start, end):
    lower, upper = parse_time(start), parse_time(end, end=True)
    if lower >= upper:
        raise ValueError("start must be before end")
    return lower, upper


def address_topic(address):
    return "0x" + "0" * 24 + validate_wallet(address)[2:]


def as_int(value):
    return int(value, 16) if isinstance(value, str) and value.startswith("0x") else int(value)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def mcp_session(call=exchange):
    session = None
    for attempt in range(5):
        try:
            _, session = call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                             "clientInfo": {"name": "audit-log-agent", "version": "1.0"}})
            break
        except HTTPError as error:
            if error.code != 429 or attempt == 4:
                raise
            clock.sleep(2 ** attempt)
    if not session:
        raise RuntimeError("Chain MCP session missing")
    request_id = 1

    def tool(name, arguments):
        nonlocal request_id
        request_id += 1
        for attempt in range(8):
            try:
                result, _ = call("tools/call", {"name": name, "arguments": arguments}, session, request_id)
                clock.sleep(0.25)
                return text(result)
            except HTTPError as error:
                if error.code != 429 or attempt == 7:
                    raise
                clock.sleep(min(30, 2 ** attempt))
        raise RuntimeError("Chain MCP retry exhausted")
    return tool


def block_at(tool, target, latest):
    """Return first block whose timestamp is at least target."""
    low, high = 0, latest + 1
    while low < high:
        middle = (low + high) // 2
        block = tool("get_block", {"block": hex(middle), "includeTransactions": False})
        if as_int(block["timestamp"]) < int(target.timestamp()):
            low = middle + 1
        else:
            high = middle
    return low


def get_logs_paged(tool, arguments, start_block, end_block):
    logs = []
    for first in range(start_block, end_block + 1, 1000):
        args = {**arguments, "fromBlock": hex(first), "toBlock": hex(min(end_block, first + 999))}
        response = tool("get_logs", args)
        page = response.get("logs", []) if isinstance(response, dict) else response
        if not isinstance(page, list):
            raise ValueError("Unexpected Chain MCP get_logs response")
        logs.extend(log for log in page if not log.get("removed"))
    return logs


def collect(wallet, start, end, max_blocks=10000, call=exchange):
    wallet = validate_wallet(wallet)
    lower, upper = parse_range(start, end)
    tool = mcp_session(call)
    chain = tool("get_chain_info", {})
    if chain.get("chainId") != CHAIN_ID or not chain.get("chainIdMatches"):
        raise RuntimeError("Chain MCP did not report Pharos mainnet")
    latest = as_int(chain["latestBlockHex"])
    first = block_at(tool, lower, latest)
    after = block_at(tool, upper, latest)
    last = min(latest, after - 1)
    if last < first:
        return first, last, [], {}, tool
    if last - first + 1 > max_blocks:
        raise ValueError(f"date range spans {last - first + 1} blocks; raise --max-blocks or narrow range")

    timestamps, txs = {}, []
    for number in range(first, last + 1):
        block = tool("get_block", {"block": hex(number), "includeTransactions": True})
        timestamps[number] = as_int(block["timestamp"])
        for tx in block.get("transactions", []):
            if tx.get("from", "").lower() == wallet or (tx.get("to") or "").lower() == wallet:
                txs.append(tx)

    topic = address_topic(wallet)
    logs = []
    queries = [
        ("transfer_in", {"topics": [TRANSFER_TOPIC, None, topic]}),
        ("transfer_out", {"topics": [TRANSFER_TOPIC, topic]}),
        ("approval", {"topics": [APPROVAL_TOPIC, topic]}),
    ]
    for kind, arguments in queries:
        for log in get_logs_paged(tool, arguments, first, last):
            logs.append({**log, "kind": kind})
            block = as_int(log["blockNumber"])
            if block not in timestamps and log.get("blockTimestamp"):
                timestamps[block] = as_int(log["blockTimestamp"])
    return first, last, txs, logs, timestamps


def classify(wallet, txs, logs, timestamps):
    wallet = validate_wallet(wallet)
    records = []
    for tx in txs:
        sender, recipient = tx.get("from", "").lower(), (tx.get("to") or "").lower()
        value, calldata = as_int(tx.get("value", 0)), tx.get("input", tx.get("data", "0x"))
        category = None
        if value and recipient == wallet:
            category = "transfers_in"
        elif value and sender == wallet and calldata in ("0x", ""):
            category = "transfers_out"
        elif sender == wallet and calldata[:10].lower() in SWAP_SELECTORS:
            category = "swaps"
        elif sender == wallet and calldata not in ("0x", ""):
            category = "contract_interactions"
        if category:
            block = as_int(tx["blockNumber"])
            records.append({"category": category, "tx_hash": tx["hash"], "block": block,
                            "transaction_index": as_int(tx.get("transactionIndex", 0)), "log_index": -1,
                            "timestamp": iso(timestamps[block]), "asset": "PROS",
                            "amount_raw": str(value) if category.startswith("transfers_") else None,
                            "counterparty": tx.get("from") if category == "transfers_in" else tx.get("to"),
                            "method_selector": calldata[:10] if calldata not in ("0x", "") else None,
                            "explorer_url": f"{EXPLORER}/tx/{tx['hash']}"})
    for log in logs:
        block, topics = as_int(log["blockNumber"]), log["topics"]
        category = {"transfer_in": "transfers_in", "transfer_out": "transfers_out", "approval": "approvals"}[log["kind"]]
        counterparty_topic = topics[1] if log["kind"] == "transfer_in" else topics[2]
        records.append({"category": category, "tx_hash": log["transactionHash"], "block": block,
                        "transaction_index": as_int(log.get("transactionIndex", 0)),
                        "log_index": as_int(log.get("logIndex", 0)), "timestamp": iso(timestamps[block]),
                        "asset": log["address"].lower(), "amount_raw": str(as_int(log["data"])),
                        "counterparty": "0x" + counterparty_topic[-40:], "method_selector": None,
                        "explorer_url": f"{EXPLORER}/tx/{log['transactionHash']}"})
    return sorted(records, key=lambda row: (row["block"], row["transaction_index"], row["log_index"], row["category"]))


def build_report(wallet, start, end, first, last, records, generated_at=None):
    totals = {category: {"count": 0, "amounts_raw": {}} for category in CATEGORIES}
    for record in records:
        total = totals[record["category"]]
        total["count"] += 1
        if record["amount_raw"] is not None:
            asset = record["asset"]
            total["amounts_raw"][asset] = str(int(total["amounts_raw"].get(asset, "0")) + int(record["amount_raw"]))
    notable = sorted(records, key=lambda row: (-int(row["amount_raw"] or 0), row["tx_hash"], row.get("log_index", -1)))[:10]
    return {"task": "audit-log-agent", "source": "Pharos Chain MCP", "read_only": True,
            "network": "Pharos mainnet", "chain_id": CHAIN_ID, "wallet": validate_wallet(wallet),
            "date_range": {"start": start, "end": end, "semantics": "UTC, start inclusive, end inclusive for date-only input"},
            "block_range": {"first": first, "last": last},
            "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
            "totals": totals, "notable_transactions": notable, "activity": records}


def export_markdown(report, output):
    labels = {category: category.replace("_", " ").capitalize() for category in CATEGORIES}
    lines = ["# Pharos Wallet Audit Log", "", f"- Wallet: `{report['wallet']}`",
             f"- Date range: `{report['date_range']['start']}` through `{report['date_range']['end']}`",
             f"- Blocks: `{report['block_range']['first']}`–`{report['block_range']['last']}`",
             "- Source: Pharos Chain MCP (read-only)", "", "## Totals", "", "| Category | Count | Raw amounts by asset |",
             "|---|---:|---|"]
    for category in CATEGORIES:
        total = report["totals"][category]
        amounts = ", ".join(f"`{asset}`: {amount}" for asset, amount in sorted(total["amounts_raw"].items())) or "—"
        lines.append(f"| {labels[category]} | {total['count']} | {amounts} |")
    lines += ["", "## Notable transactions", "", "| Time (UTC) | Category | Amount (raw) | Asset | Transaction |", "|---|---|---:|---|---|"]
    for row in report["notable_transactions"]:
        lines.append(f"| {row['timestamp']} | {labels[row['category']]} | {row['amount_raw'] or '—'} | `{row['asset']}` | [{row['tx_hash']}]({row['explorer_url']}) |")
    lines += ["", "## Activity", "", "```json", json.dumps(report["activity"], indent=2), "```", ""]
    output.write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wallet")
    parser.add_argument("start", help="ISO-8601 date/time; date-only means 00:00 UTC")
    parser.add_argument("end", help="ISO-8601 date/time; date-only includes whole UTC day")
    parser.add_argument("--output", type=Path, default=Path("audit-log-report.md"))
    parser.add_argument("--json", type=Path, help="Optional JSON evidence output")
    parser.add_argument("--max-blocks", type=int, default=10000)
    args = parser.parse_args()
    if args.max_blocks < 1:
        parser.error("--max-blocks must be positive")
    first, last, txs, logs, timestamps = collect(args.wallet, args.start, args.end, args.max_blocks)
    report = build_report(args.wallet, args.start, args.end, first, last, classify(args.wallet, txs, logs, timestamps))
    export_markdown(report, args.output)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "records": len(report["activity"]), "totals": report["totals"]}, indent=2))


if __name__ == "__main__":
    main()

"""Explainable, read-only Pharos wallet risk checker backed by Chain MCP."""
import argparse
import json
import re
from urllib.request import Request, urlopen

MCP_URL = "https://mcp.pharos.xyz/mcp"
APPROVAL_TOPIC = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")


def normalize_address(value):
    if not ADDRESS.fullmatch(value):
        raise ValueError("address must be a 0x-prefixed 20-byte hex value")
    return value.lower()


def _integer(value):
    return int(value, 0) if isinstance(value, str) else int(value)


def validate_block(requested, latest):
    if requested is None:
        return latest
    if requested < 0 or requested > latest:
        raise ValueError("snapshot block must be between zero and latest block")
    return requested


def _post(method, params, session=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session:
        headers["Mcp-Session-Id"] = session
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = Request(MCP_URL, body, headers, method="POST")
    with urlopen(request, timeout=30) as response:
        text = response.read().decode()
        session = response.headers.get("Mcp-Session-Id") or session
    if text.startswith("event:"):
        text = next(line[6:] for line in text.splitlines() if line.startswith("data: "))
    reply = json.loads(text)
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"], session


def _tool(name, arguments, session):
    result, _ = _post("tools/call", {"name": name, "arguments": arguments}, session)
    if result.get("isError"):
        raise RuntimeError(result["content"])
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def collect(address, window, flagged, to_block=None):
    address = normalize_address(address)
    result, session = _post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                             "clientInfo": {"name": "wallet-risk-checker", "version": "1.0"}})
    if not session or "serverInfo" not in result:
        raise RuntimeError("Chain MCP initialization failed")
    chain = _tool("get_chain_info", {}, session)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("unexpected chain")
    latest = validate_block(to_block, _integer(chain["latestBlock"]))
    first = max(0, latest - window + 1)
    balance = _tool("get_balance", {"address": address, "block": latest}, session)
    nonce = _tool("get_transaction_count", {"address": address, "block": latest}, session)
    code = _tool("get_code", {"address": address, "block": latest}, session)
    padded_owner = "0x" + "0" * 24 + address[2:]
    approvals = _tool("get_logs", {"topics": [APPROVAL_TOPIC, padded_owner],
                                    "fromBlock": first, "toBlock": latest}, session)
    logs = approvals.get("logs", approvals) if isinstance(approvals, dict) else approvals
    incoming = outgoing = 0
    flagged_hits = set()
    flagged = {normalize_address(item) for item in flagged}
    for number in range(first, latest + 1):
        block = _tool("get_block", {"block": number, "includeTransactions": True}, session)
        for transaction in block.get("transactions", []):
            sender = (transaction.get("from") or "").lower()
            receiver = (transaction.get("to") or "").lower()
            if sender == address:
                outgoing += 1
                if receiver in flagged:
                    flagged_hits.add(receiver)
            if receiver == address:
                incoming += 1
                if sender in flagged:
                    flagged_hits.add(sender)
    spenders = {"0x" + item["topics"][2][-40:].lower() for item in logs if len(item.get("topics", [])) > 2}
    return {
        "balance_wei": _integer(balance.get("balanceWei", balance.get("balance", 0))),
        "nonce": _integer(nonce.get("transactionCount", nonce.get("nonce", 0))),
        "code": code.get("code", code.get("bytecode", "0x")),
        "incoming": incoming, "outgoing": outgoing,
        "approval_count": len(logs), "unique_spenders": len(spenders),
        "flagged_interactions": sorted(flagged_hits), "window_from": first, "window_to": latest,
        "chain": {"name": chain["name"], "chain_id": chain["chainId"]},
        "provenance": {"provider": "Pharos Chain MCP", "endpoint": MCP_URL,
                       "tools": ["get_chain_info", "get_balance", "get_transaction_count",
                                 "get_code", "get_logs", "get_block"]},
    }


def analyze(address, facts):
    address = normalize_address(address)
    code = facts["code"] not in ("0x", "0x0", "")
    positive = facts["balance_wei"] > 0
    signals = [
        {"name": "contract_code", "value": code, "flagged": False,
         "plain_language": "Bytecode exists, so this address is a contract." if code else "No bytecode exists, so this address is an externally owned wallet."},
        {"name": "native_balance", "value_wei": facts["balance_wei"], "flagged": False,
         "plain_language": f"Wallet holds {facts['balance_wei']} wei of native PROS."},
        {"name": "outgoing_nonce", "value": facts["nonce"], "flagged": False,
         "plain_language": f"Wallet has submitted {facts['nonce']} confirmed outgoing transactions over its lifetime."},
        {"name": "recent_activity", "incoming": facts["incoming"], "outgoing": facts["outgoing"], "flagged": False,
         "plain_language": f"Last {facts['window_to'] - facts['window_from'] + 1} blocks contain {facts['incoming']} incoming and {facts['outgoing']} outgoing transactions."},
        {"name": "approval_pattern", "approvals": facts["approval_count"], "unique_spenders": facts["unique_spenders"], "flagged": False,
         "plain_language": f"Recent logs contain {facts['approval_count']} token approvals to {facts['unique_spenders']} unique spenders."},
        {"name": "flagged_address_interaction", "addresses": facts["flagged_interactions"], "flagged": False,
         "plain_language": "No recent direct transaction involved a configured flagged address."},
    ]
    reasons = []
    score = 0
    if not code and positive and facts["nonce"] == 0 and facts["incoming"] > 0:
        score += 2
        signals[2]["flagged"] = True
        reasons.append("Freshly funded wallet: it has funds and a recent incoming transfer but lifetime outgoing nonce is zero.")
    if not code and positive and facts["incoming"] > 0 and facts["outgoing"] == 0:
        score += 1
        signals[3]["flagged"] = True
        reasons.append("No outgoing transaction appears in the inspected window despite incoming funds.")
    if facts["approval_count"] >= 3 and facts["unique_spenders"] >= 2:
        score += 3
        signals[4]["flagged"] = True
        reasons.append(f"Unusual approval pattern: {facts['approval_count']} approvals target {facts['unique_spenders']} spenders in the inspected window.")
    if facts["flagged_interactions"]:
        score += 4
        signals[5]["flagged"] = True
        signals[5]["plain_language"] = "Recent direct transactions involved configured flagged addresses: " + ", ".join(facts["flagged_interactions"]) + "."
        reasons.append("Recent interaction with configured flagged address(es): " + ", ".join(facts["flagged_interactions"]) + ".")
    level = "high" if score >= 3 else "medium" if score else "low"
    return {"address": address, "risk_level": level, "score": score,
            "reasons": reasons or ["No risk rules fired in available on-chain signals."],
            "signals": signals, "rules": {"medium": "score 1-2", "high": "score 3 or more"},
            "limitations": ["Code presence is observable; source-code verification is not exposed by Chain MCP.",
                            "Activity and approvals are limited to the selected recent block window."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("address")
    parser.add_argument("--window", type=int, default=20, help="Recent blocks to inspect (1-1000)")
    parser.add_argument("--flagged", action="append", default=[], help="Known-risk address; repeatable")
    parser.add_argument("--to-block", type=int, help="Historical end block; defaults to latest")
    args = parser.parse_args()
    if not 1 <= args.window <= 1000:
        parser.error("window must be between 1 and 1000")
    facts = collect(args.address, args.window, args.flagged, args.to_block)
    report = analyze(args.address, facts)
    report["evidence"] = facts
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

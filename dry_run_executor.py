"""Simulate a Pharos transaction through Chain MCP. Never signs or broadcasts."""
import argparse
import json
import re
from urllib.request import Request, urlopen

MCP = "https://mcp.pharos.xyz/mcp"
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
HEX = re.compile(r"^0x(?:[0-9a-fA-F]{2})*$")
QUANTITY = re.compile(r"^0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)$")


class ToolError(RuntimeError):
    def __init__(self, message, details=None):
        super().__init__(message)
        self.details = details


def post(method, params, session=None, request_id=1):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session:
        headers["Mcp-Session-Id"] = session
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    request = Request(MCP, json.dumps(payload).encode(), headers, method="POST")
    with urlopen(request, timeout=25) as response:
        body = response.read().decode()
        session = response.headers.get("Mcp-Session-Id") or session
    if body.startswith("event:"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    reply = json.loads(body)
    if "error" in reply:
        raise ToolError(str(reply["error"]), reply["error"])
    return reply["result"], session


def connect():
    _, session = post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "dry-run-executor", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")

    def call(name, arguments):
        result, _ = post("tools/call", {"name": name, "arguments": arguments}, session, 2)
        texts = [part["text"] for part in result.get("content", []) if part.get("type") == "text"]
        value = json.loads(texts[0]) if texts else None
        if result.get("isError"):
            raise ToolError(_error_message(value), value)
        if not isinstance(value, dict):
            raise ToolError("Unexpected MCP tool response", value)
        return value

    return call


def _error_message(value):
    if isinstance(value, dict):
        error = value.get("error", value)
        if isinstance(error, dict):
            return str(error.get("message", error))
        return str(error)
    return str(value)


def _quantity(value, field):
    if not isinstance(value, str) or not QUANTITY.fullmatch(value):
        raise ValueError(f"{field} must be a canonical 0x quantity")
    return int(value, 16)


def validate(tx):
    if not isinstance(tx, dict):
        raise ValueError("transaction must be a JSON object")
    allowed = {"from", "to", "data", "value", "gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas", "nonce"}
    unknown = set(tx) - allowed
    if unknown:
        raise ValueError("unsupported transaction fields: " + ", ".join(sorted(unknown)))
    if not ADDRESS.fullmatch(str(tx.get("to", ""))):
        raise ValueError("to must be a 0x-prefixed 20-byte address")
    if "from" in tx and not ADDRESS.fullmatch(str(tx["from"])):
        raise ValueError("from must be a 0x-prefixed 20-byte address")
    if "data" in tx and (not isinstance(tx["data"], str) or not HEX.fullmatch(tx["data"])):
        raise ValueError("data must be 0x-prefixed, even-length hex")
    for field in ("value", "gas", "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas", "nonce"):
        if field in tx:
            _quantity(tx[field], field)
    return dict(tx)


def _hex_result(reply, *keys):
    for key in keys:
        value = reply.get(key)
        if isinstance(value, str) and value.startswith("0x"):
            return value
    raise ToolError("MCP response lacks hex result", reply)


def _integer_result(reply, decimal_keys, hex_keys):
    for key in decimal_keys:
        value = reply.get(key)
        if isinstance(value, (str, int)) and str(value).isdigit():
            return int(value)
    return int(_hex_result(reply, *hex_keys), 16)


def _find_revert_data(value):
    if isinstance(value, str):
        match = re.search(r"0x[0-9a-fA-F]{8,}", value)
        return match.group(0) if match else None
    if isinstance(value, dict):
        for key in ("data", "result", "error", "originalError"):
            found = _find_revert_data(value.get(key))
            if found:
                return found
        for item in value.values():
            found = _find_revert_data(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_revert_data(item)
            if found:
                return found
    return None


def decode_revert(details, fallback):
    raw = _find_revert_data(details)
    if raw:
        data = bytes.fromhex(raw[2:])
        if data[:4] == bytes.fromhex("08c379a0") and len(data) >= 68:
            offset = int.from_bytes(data[4:36], "big")
            start = 4 + offset
            if start + 32 <= len(data):
                size = int.from_bytes(data[start:start + 32], "big")
                text = data[start + 32:start + 32 + size]
                if len(text) == size:
                    return text.decode("utf-8", "replace")
        if data[:4] == bytes.fromhex("4e487b71") and len(data) >= 36:
            return f"Panic(0x{int.from_bytes(data[4:36], 'big'):x})"
        return raw
    match = re.search(r"execution reverted(?:\:\s*([^'\"}\]]+))?", fallback, re.I)
    reason = match.group(1).strip() if match and match.group(1) else ""
    return reason or None


def _blocked(base, error):
    base.update({"simulation": {"status": "revert", "return_data": None,
                                "revert_reason": decode_revert(error.details, str(error))},
                 "gas": {"estimate": None, "price_wei": None, "estimated_cost_wei": None}})
    base["outcome"]["expected"] = "No state change; transaction blocked after failed simulation."
    base["execution"].update({"blocked": True, "reason": "simulation_failed"})
    return base


def simulate(transaction, tool):
    tx = validate(transaction)
    chain = tool("get_chain_info", {})
    if chain.get("chainId") != 1672 or not chain.get("chainIdMatches"):
        raise RuntimeError("Unexpected chain; required Pharos mainnet chain ID 1672")
    block = chain.get("latestBlockHex") or hex(int(chain["latestBlock"]))
    value = _quantity(tx.get("value", "0x0"), "value")
    before = {}
    for role in ("from", "to"):
        address = tx.get(role)
        if address and address.lower() not in [item.get("address", "").lower() for item in before.values()]:
            reply = tool("get_balance", {"address": address, "block": block})
            balance = _integer_result(reply, ("balanceWei", "balance"), ("balanceHex", "balance", "result"))
            before[role] = {"address": address, "balance_wei": str(balance)}
    base = {"network": "Pharos mainnet", "chain_id": 1672, "block": int(block, 16),
            "transaction": tx, "outcome": {"before": before},
            "execution": {"broadcast_available": False, "blocked": False, "reason": None}}
    try:
        call_result = _hex_result(tool("eth_call", {"transaction": tx, "block": block}), "result")
    except ToolError as error:
        return _blocked(base, error)
    try:
        estimate_reply = tool("estimate_gas", {"transaction": tx})
    except ToolError as error:
        return _blocked(base, error)
    estimate = _integer_result(estimate_reply, ("gas", "gasEstimate"), ("gasHex", "gas", "gasEstimate", "result"))
    price_reply = tool("get_gas_price", {})
    price = _integer_result(price_reply, ("gasPriceWei",), ("gasPriceHex", "gasPrice", "result"))
    cost = estimate * price
    expected = {"return_data": call_result}
    if "from" in before:
        expected["from_balance_wei"] = str(int(before["from"]["balance_wei"]) - value - cost)
    if "to" in before:
        expected["to_balance_wei"] = str(int(before["to"]["balance_wei"]) + value)
    base.update({"simulation": {"status": "success", "return_data": call_result, "revert_reason": None},
                 "gas": {"estimate": estimate, "price_wei": str(price), "estimated_cost_wei": str(cost)}})
    base["outcome"]["expected"] = expected
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("transaction", help="JSON transaction object or @path to JSON file")
    args = parser.parse_args()
    text = open(args.transaction[1:], encoding="utf-8").read() if args.transaction.startswith("@") else args.transaction
    report = simulate(json.loads(text), connect())
    print(json.dumps(report, indent=2))
    raise SystemExit(2 if report["execution"]["blocked"] else 0)


if __name__ == "__main__":
    main()

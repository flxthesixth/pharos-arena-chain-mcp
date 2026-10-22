"""Evaluate configurable thresholds against live Pharos Chain MCP reads."""
import argparse
import json
import operator
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.request import Request, urlopen

MCP = "https://mcp.pharos.xyz/mcp"
USDC = "0xc879c018db60520f4355c26ed1a6d572cdac1815"
TOTAL_SUPPLY = "0x18160ddd"
OPERATORS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le, "==": operator.eq}
METRICS = {"block_number", "gas_price_gwei", "usdc_total_supply"}


def exchange(method, params, session=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    request = Request(MCP, json.dumps(payload).encode(), headers, method="POST")
    with urlopen(request, timeout=20) as response:
        body = response.read().decode()
        new_session = response.headers.get("Mcp-Session-Id")
    if body.startswith("event: message\n"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    message = json.loads(body)
    if "error" in message:
        raise RuntimeError(message["error"])
    return message["result"], new_session


def tool_text(result):
    if result.get("isError"):
        raise RuntimeError(result["content"])
    return json.loads(next(part["text"] for part in result["content"] if part["type"] == "text"))


def read_chain(call=exchange):
    _, session = call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "threshold-guardian", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")

    def run(name, arguments, request_id):
        result, _ = call("tools/call", {"name": name, "arguments": arguments}, session, request_id)
        return tool_text(result)

    chain = run("get_chain_info", {}, 2)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    block = chain["latestBlockHex"]
    gas = run("get_gas_price", {}, 3)
    supply = run("eth_call", {"transaction": {"to": USDC, "data": TOTAL_SUPPLY}, "block": block}, 4)
    return {
        "block_number": int(block, 16),
        "gas_price_gwei": str(gas["gasPriceGwei"]),
        "usdc_total_supply": str(Decimal(int(supply["result"], 16)) / Decimal(10**6)),
    }


def evaluate(values, conditions):
    if len(conditions) < 3:
        raise ValueError("At least 3 conditions required")
    trace = []
    for condition in conditions:
        metric = condition.get("metric")
        comparison = condition.get("operator")
        if metric not in METRICS:
            raise ValueError(f"Unknown metric: {metric}")
        if comparison not in OPERATORS:
            raise ValueError(f"Unknown operator: {comparison}")
        try:
            value = Decimal(str(values[metric]))
            threshold = Decimal(str(condition["threshold"]))
        except (InvalidOperation, KeyError) as error:
            raise ValueError(f"Invalid threshold for {metric}") from error
        trace.append({"metric": metric, "value": str(values[metric]), "operator": comparison,
                      "threshold": str(condition["threshold"]),
                      "passed": OPERATORS[comparison](value, threshold)})
    return {"conditions": trace, "decision": "FIRE" if all(item["passed"] for item in trace) else "HOLD"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="threshold_guardian_config.json")
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    try:
        conditions = config["profiles"][args.profile]
    except KeyError as error:
        raise SystemExit(f"Unknown profile: {args.profile}") from error
    values = read_chain()
    result = evaluate(values, conditions)
    print(json.dumps({"network": "Pharos mainnet", "chain_id": 1672, "block": values["block_number"],
                      "profile": args.profile, **result}, indent=2))


if __name__ == "__main__":
    main()

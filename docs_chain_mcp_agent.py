"""Explain ERC-20 reads with Docs MCP, then execute them with Chain MCP."""
import argparse
import json
import re
from datetime import datetime, timezone
from decimal import Decimal

from arena_contract_state import CONTRACT, SELECTORS, exchange, text
from pharos_docs import ask

DOC_QUERIES = {
    "decimals": (
        "What does the ERC-20 decimals() function return, and how should its value "
        "be used to interpret token amounts? Include sources."
    ),
    "totalSupply": (
        "What does the ERC-20 totalSupply() function return, and how should it be "
        "interpreted with token decimals? Include sources."
    ),
}
SOURCE_RE = re.compile(r"https://docs\.pharos\.xyz/[\w./-]+")


def sourced_explanation(function, docs_ask=ask):
    raw = docs_ask(DOC_QUERIES[function])
    sources = list(dict.fromkeys(SOURCE_RE.findall(raw)))
    if not sources:
        raise RuntimeError(f"Docs MCP returned no Pharos docs source for {function}()")
    if function.lower() not in raw.lower():
        raise RuntimeError(f"Docs MCP answer did not explain {function}()")
    return {"query": DOC_QUERIES[function], "answer": raw, "sources": sources}


def run_agent(docs_ask=ask, chain_exchange=exchange):
    explanations = {name: sourced_explanation(name, docs_ask) for name in DOC_QUERIES}
    _, session = chain_exchange(
        "initialize",
        {"protocolVersion": "2025-03-26", "capabilities": {},
         "clientInfo": {"name": "docs-chain-mcp-agent", "version": "1.0"}},
    )
    if not session:
        raise RuntimeError("Chain MCP session missing")

    def chain_tool(name, arguments, request_id):
        result, _ = chain_exchange(
            "tools/call", {"name": name, "arguments": arguments}, session, request_id
        )
        return text(result)

    chain = chain_tool("get_chain_info", {}, 2)
    if chain.get("chainId") != 1672 or not chain.get("chainIdMatches"):
        raise RuntimeError("Chain MCP did not report Pharos mainnet")
    block_hex = chain["latestBlockHex"]
    raw = {}
    for request_id, function in enumerate(DOC_QUERIES, 3):
        raw[function] = chain_tool(
            "eth_call",
            {"transaction": {"to": CONTRACT, "data": SELECTORS[function]}, "block": block_hex},
            request_id,
        )["result"]

    decimals = int(raw["decimals"], 16)
    total_supply_raw = int(raw["totalSupply"], 16)
    if not 0 <= decimals <= 36:
        raise ValueError("Unexpected token decimals")
    total_supply = Decimal(total_supply_raw).scaleb(-decimals)
    calls = [
        {
            "function": "decimals()",
            "selector": SELECTORS["decimals"],
            "docs_mcp": explanations["decimals"],
            "chain_mcp": {"tool": "eth_call", "raw_result": raw["decimals"], "decoded": decimals},
            "interpretation": (
                f"USDC reports {decimals} decimals, so one displayed USDC equals "
                f"10^{decimals} raw units."
            ),
        },
        {
            "function": "totalSupply()",
            "selector": SELECTORS["totalSupply"],
            "docs_mcp": explanations["totalSupply"],
            "chain_mcp": {
                "tool": "eth_call",
                "raw_result": raw["totalSupply"],
                "decoded": str(total_supply_raw),
            },
            "interpretation": (
                f"Docs say scale totalSupply by decimals(); {total_supply_raw} raw units "
                f"at {decimals} decimals equal {format(total_supply, 'f')} USDC."
            ),
        },
    ]
    return {
        "task": "docs-chain-mcp-agent",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "network": "Pharos mainnet",
        "chain_id": chain["chainId"],
        "block": int(block_hex, 16),
        "contract": CONTRACT,
        "read_only": True,
        "calls": calls,
    }


def self_test():
    docs = {
        "decimals": "decimals() returns uint8.\n# Sources\nhttps://docs.pharos.xyz/token",
        "totalSupply": "totalSupply() returns uint256.\n# Sources\nhttps://docs.pharos.xyz/token",
    }

    def fake_docs(question):
        return docs["decimals" if "decimals() function" in question else "totalSupply"]

    values = {SELECTORS["decimals"]: hex(6), SELECTORS["totalSupply"]: hex(123450000)}

    def fake_chain(method, params, session=None, request_id=1):
        if method == "initialize":
            return {}, "test-session"
        if params["name"] == "get_chain_info":
            value = {"chainId": 1672, "chainIdMatches": True, "latestBlockHex": "0xa"}
        else:
            args = params["arguments"]
            assert args["block"] == "0xa" and args["transaction"]["to"] == CONTRACT
            value = {"result": values[args["transaction"]["data"]]}
        return {"content": [{"type": "text", "text": json.dumps(value)}]}, None

    result = run_agent(fake_docs, fake_chain)
    assert result["block"] == 10 and len(result["calls"]) == 2
    assert result["calls"][0]["chain_mcp"]["decoded"] == 6
    assert "123.450000 USDC" in result["calls"][1]["interpretation"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", help="Also write JSON evidence to this path")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    result = run_agent()
    rendered = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as output:
            output.write(rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()

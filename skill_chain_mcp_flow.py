"""Run one request through Chain MCP and Pharos Skill Engine read procedure."""
import argparse
import json
import subprocess

from arena_contract_state import CONTRACT
from threshold_guardian import exchange, tool_text

RPC = "https://rpc.pharos.xyz"
SKILL_SOURCE = "pharos-skill-engine/references/query.md#contract-read-only-call"


def chain_snapshot():
    _, session = exchange("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                         "clientInfo": {"name": "skill-chain-flow", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")

    def call(name, arguments, request_id):
        result, _ = exchange("tools/call", {"name": name, "arguments": arguments}, session, request_id)
        return tool_text(result)

    chain = call("get_chain_info", {}, 2)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    block = chain["latestBlockHex"]
    result = call("eth_call", {"transaction": {"to": CONTRACT, "data": "0x313ce567"}, "block": block}, 3)
    return int(block, 16), int(result["result"], 16)


def skill_read(contract, block):
    command = ["cast", "call", contract, "decimals()(uint8)", "--block", str(block), "--rpc-url", RPC]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=30, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or "Skill Engine read failed")
    return int(completed.stdout.strip().split()[0]), command


def run(request):
    if request.strip().lower() != "verify the live usdc decimals through chain mcp and skill engine":
        raise ValueError("Supported request: verify the live USDC decimals through Chain MCP and Skill Engine")
    block, mcp_value = chain_snapshot()
    skill_value, command = skill_read(CONTRACT, block)
    return {
        "request": request,
        "flow": [
            "Chain MCP verifies chain ID and reads decimals() at a fixed block",
            "Pharos Skill Engine Read Contract procedure receives the same contract and block",
            "The flow compares both decoded outputs and reports verification",
        ],
        "chain_mcp": {"block": block, "contract": CONTRACT, "function": "decimals()", "value": mcp_value},
        "skill_engine": {"source": SKILL_SOURCE, "procedure": "Read Contract", "command": command,
                         "input_from_chain_mcp": {"block": block, "contract": CONTRACT}, "value": skill_value},
        "result": {"verified": mcp_value == skill_value, "interpretation": f"USDC uses {skill_value} decimals."},
    }


def self_test():
    request = "verify the live USDC decimals through Chain MCP and Skill Engine"
    try:
        run("unsupported")
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported request accepted")
    assert request.lower().startswith("verify")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", nargs="?", default="verify the live USDC decimals through Chain MCP and Skill Engine")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); print("self-test passed"); return
    report = run(args.request)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["result"]["verified"] else 1)


if __name__ == "__main__":
    main()

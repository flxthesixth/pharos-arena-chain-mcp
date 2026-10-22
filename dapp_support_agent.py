"""Diagnose a failed Pharos transaction through Chain MCP."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from arena_contract_state import exchange

HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}\Z")
EXPLORER = "https://www.pharosscan.xyz/tx/"


def mcp_text(result):
    part = next((item for item in result.get("content", []) if item.get("type") == "text"), None)
    if not part:
        raise RuntimeError("Chain MCP returned no text content")
    return json.loads(part["text"])


def decode_error_string(data):
    if not isinstance(data, str) or not data.startswith("0x08c379a0"):
        return None
    try:
        raw = bytes.fromhex(data[10:])
        offset = int.from_bytes(raw[:32], "big")
        size = int.from_bytes(raw[offset:offset + 32], "big")
        return raw[offset + 32:offset + 32 + size].decode()
    except (ValueError, UnicodeDecodeError):
        return None


def classify(tx, receipt, replay):
    error = replay.get("error", {})
    message = error.get("message", "")
    reason = decode_error_string(error.get("data"))
    combined = f"{message} {reason or ''}".lower()
    gas = int(tx["gas"], 16)
    gas_used = int(receipt["gasUsed"], 16)
    if ("not have enough funds" in combined or "not enough funds" in combined or
            "insufficient funds" in combined):
        return {
            "failure_type": "insufficient_native_balance",
            "technical_cause": message,
            "plain_explanation": "Sender did not have enough PROS to cover transfer value and network fee.",
            "suggested_fix": "Add PROS or send a smaller amount, then estimate the fee before retrying.",
        }
    if reason and "slippage" in reason.lower():
        return {
            "failure_type": "slippage_limit_exceeded",
            "technical_cause": f"Contract reverted with reason: {reason}",
            "plain_explanation": "Swap price moved outside the minimum return accepted by this transaction.",
            "suggested_fix": "Refresh the quote and retry with a current minimum return; raise slippage only if the risk is acceptable.",
        }
    if reason:
        return {
            "failure_type": "application_revert",
            "technical_cause": f"Contract reverted with reason: {reason}",
            "plain_explanation": f"Contract rejected the requested action: {reason}.",
            "suggested_fix": "Correct the rejected input or contract state, simulate again, then retry.",
        }
    if gas_used == gas:
        return {
            "failure_type": "out_of_gas",
            "technical_cause": f"Receipt consumed full gas limit ({gas_used}).",
            "plain_explanation": "Transaction ran out of execution budget before it could finish.",
            "suggested_fix": "Estimate gas against current state and retry with a safe buffer.",
        }
    return {
        "failure_type": "unidentified_revert",
        "technical_cause": message or f"Revert data: {error.get('data', 'unavailable')}",
        "plain_explanation": "Contract rejected the action, but did not provide a readable reason.",
        "suggested_fix": "Decode custom error with contract ABI and simulate the same call before retrying.",
    }


def diagnose(tx_hash, chain_exchange=exchange):
    if not HASH_RE.fullmatch(tx_hash):
        raise ValueError("Transaction hash must be 0x followed by 64 hexadecimal characters")
    _, session = chain_exchange(
        "initialize",
        {"protocolVersion": "2025-03-26", "capabilities": {},
         "clientInfo": {"name": "dapp-support-agent", "version": "1.0"}},
    )
    if not session:
        raise RuntimeError("Chain MCP session missing")

    def tool(name, arguments, request_id):
        result, _ = chain_exchange(
            "tools/call", {"name": name, "arguments": arguments}, session, request_id
        )
        return mcp_text(result)

    tx = tool("get_transaction", {"hash": tx_hash}, 2)
    receipt = tool("get_transaction_receipt", {"hash": tx_hash}, 3)
    if not tx or not receipt:
        raise LookupError("Transaction or receipt not found")
    if receipt.get("status") != "0x0":
        raise ValueError("Transaction did not fail")
    replay_tx = {"from": tx["from"], "to": tx["to"], "value": tx["value"], "data": tx["input"]}
    replay_block = hex(int(tx["blockNumber"], 16) - 1)
    replay = tool("eth_call", {"transaction": replay_tx, "block": replay_block}, 4)
    diagnosis = classify(tx, receipt, replay)
    return {
        "task": "dapp-support-agent",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "network": "Pharos mainnet",
        "chain_id": int(tx["chainId"], 16),
        "tx_hash": tx_hash,
        "explorer": EXPLORER + tx_hash,
        "chain_mcp": {
            "transaction_tool": "get_transaction",
            "receipt_tool": "get_transaction_receipt",
            "replay_tool": "eth_call",
            "replay_block": replay_block,
            "transaction": tx,
            "receipt": receipt,
            "replay": replay,
        },
        "diagnosis": diagnosis,
        "read_only": True,
    }


def self_test():
    assert decode_error_string("0x08c379a0" + (32).to_bytes(32, "big").hex() +
                               (8).to_bytes(32, "big").hex() + b"SLIPPAGE".hex().ljust(64, "0")) == "SLIPPAGE"
    tx = {"gas": "0x5208"}
    receipt = {"gasUsed": "0x5208"}
    assert classify(tx, receipt, {"error": {"message": "not enough funds"}})["failure_type"] == "insufficient_native_balance"
    assert classify(tx, receipt, {})["failure_type"] == "out_of_gas"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tx_hash", nargs="?")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    if not args.tx_hash:
        parser.error("tx_hash is required unless --self-test is used")
    result = diagnose(args.tx_hash.lower())
    rendered = json.dumps(result, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()

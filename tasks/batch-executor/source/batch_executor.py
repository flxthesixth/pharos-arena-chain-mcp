"""Prepare and simulate one Multicall3 transaction. Never signs or broadcasts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import shlex
import socket
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

RPC_URL = "https://rpc.pharos.xyz"
CHAIN_ID = 1672
MULTICALL3 = "0xca11bde05977b3631167028862be2a173976ca11"
AGGREGATE3_SELECTOR = "82ad56cb"
GET_CHAIN_ID_SELECTOR = "3408e470"
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
CALLDATA = re.compile(r"^0x(?:[0-9a-fA-F]{2})*$")
HEX_DATA = re.compile(r"^0x(?:[0-9a-fA-F]{2})*$")


class RPCError(RuntimeError):
    """JSON-RPC transport, protocol, or remote error."""


class RPCRemoteError(RPCError):
    """JSON-RPC error object returned by endpoint."""


class AggregateRevert(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


class AggregateResultError(RuntimeError):
    def __init__(self, message, evidence):
        super().__init__(message)
        self.evidence = evidence


def word(value):
    return value.to_bytes(32, "big")


def padded(data):
    return data + b"\0" * (-len(data) % 32)


def validate_actions(actions):
    if not isinstance(actions, list) or len(actions) < 3:
        raise ValueError("actions must be a JSON list with at least 3 entries")
    clean = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"action {index} must be an object")
        unknown = set(action) - {"label", "target", "allow_failure", "data"}
        if unknown:
            raise ValueError(f"action {index} has unsupported fields: {', '.join(sorted(unknown))}")
        target = action.get("target")
        data = action.get("data")
        allow_failure = action.get("allow_failure", False)
        if not isinstance(target, str) or not ADDRESS.fullmatch(target):
            raise ValueError(f"action {index} target must be a 20-byte address")
        if not isinstance(data, str) or not CALLDATA.fullmatch(data):
            raise ValueError(f"action {index} data must be even-length 0x hex")
        if not isinstance(allow_failure, bool):
            raise ValueError(f"action {index} allow_failure must be boolean")
        label = action.get("label", f"action-{index + 1}")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"action {index} label must be a non-empty string")
        clean.append({"label": label, "target": target.lower(), "allow_failure": allow_failure, "data": data.lower()})
    return clean


def encode_aggregate3(actions):
    bodies = []
    for action in actions:
        data = bytes.fromhex(action["data"][2:])
        bodies.append(word(int(action["target"], 16)) + word(action["allow_failure"]) + word(96) + word(len(data)) + padded(data))
    offsets, cursor = [], 32 * len(bodies)
    for body in bodies:
        offsets.append(word(cursor))
        cursor += len(body)
    array = word(len(bodies)) + b"".join(offsets) + b"".join(bodies)
    return "0x" + AGGREGATE3_SELECTOR + (word(32) + array).hex()


def _word_at(data, offset, name):
    if offset < 0 or offset % 32 or offset + 32 > len(data):
        raise ValueError(f"aggregate3 {name} out of bounds")
    return int.from_bytes(data[offset:offset + 32], "big")


def decode_aggregate3(raw, count):
    if not isinstance(raw, str) or not HEX_DATA.fullmatch(raw):
        raise ValueError("aggregate3 returned malformed hex data")
    data = bytes.fromhex(raw[2:])
    if len(data) < 64:
        raise ValueError("short aggregate3 return data")
    root = _word_at(data, 0, "root offset")
    length = _word_at(data, root, "root offset")
    if length != count:
        raise ValueError(f"aggregate3 returned {length} results for {count} actions")
    base = root + 32
    if base + 32 * length > len(data):
        raise ValueError("aggregate3 result offsets out of bounds")
    results = []
    for index in range(length):
        relative = _word_at(data, base + index * 32, "item offset")
        item = base + relative
        success_value = _word_at(data, item, "item offset")
        if success_value not in (0, 1):
            raise ValueError("aggregate3 success value is not boolean")
        blob_relative = _word_at(data, item + 32, "blob offset")
        blob_at = item + blob_relative
        size = _word_at(data, blob_at, "blob offset")
        blob_start = blob_at + 32
        padded_end = blob_start + ((size + 31) // 32) * 32
        if padded_end > len(data):
            raise ValueError("truncated aggregate3 result")
        blob = data[blob_start:blob_start + size]
        results.append({"success": bool(success_value), "return_data": "0x" + blob.hex()})
    return results


def rpc(method, params, url=RPC_URL):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = Request(url, payload, {"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read()
    except (socket.timeout, TimeoutError) as exc:
        raise RPCError(f"RPC request timed out: {exc}") from exc
    except HTTPError as exc:
        raise RPCError(f"RPC HTTP error {exc.code}: {exc.reason}") from exc
    except URLError as exc:
        raise RPCError(f"RPC network error: {exc.reason}") from exc
    except OSError as exc:
        raise RPCError(f"RPC network error: {exc}") from exc
    try:
        reply = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RPCError("RPC returned malformed JSON") from exc
    if not isinstance(reply, dict):
        raise RPCError("RPC response must be a JSON object")
    if "error" in reply:
        error = reply["error"]
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise RPCRemoteError(message)
    if "result" not in reply:
        raise RPCError("RPC response missing result")
    return reply["result"]


def _hex_quantity(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        raise RPCError(f"RPC returned invalid {name}")
    return int(value, 16)


def _capture_chain_evidence(rpc_call, endpoint, command):
    chain_id = _hex_quantity(rpc_call("eth_chainId", []), "chain ID")
    if chain_id != CHAIN_ID:
        raise RuntimeError(f"unexpected chain; required Pharos mainnet chain ID {CHAIN_ID}")
    block = rpc_call("eth_getBlockByNumber", ["latest", False])
    if not isinstance(block, dict):
        raise RPCError("RPC returned invalid latest block")
    number, block_hash, timestamp = block.get("number"), block.get("hash"), block.get("timestamp")
    _hex_quantity(number, "block number")
    _hex_quantity(timestamp, "block timestamp")
    if not isinstance(block_hash, str) or not re.fullmatch(r"0x[0-9a-fA-F]{64}", block_hash):
        raise RPCError("RPC returned invalid block hash")
    code = rpc_call("eth_getCode", [MULTICALL3, number])
    if not isinstance(code, str) or not HEX_DATA.fullmatch(code):
        raise RPCError("RPC returned malformed Multicall3 bytecode")
    if code == "0x" or not bytes.fromhex(code[2:]).strip(b"\0"):
        raise RuntimeError(f"Multicall3 has no bytecode at pinned block {number}")
    chain_result = rpc_call("eth_call", [{"to": MULTICALL3, "data": "0x" + GET_CHAIN_ID_SELECTOR}, number])
    if not isinstance(chain_result, str) or not HEX_DATA.fullmatch(chain_result) or len(chain_result) != 66:
        raise RPCError("Multicall3 getChainId() returned malformed data")
    multicall_chain_id = int(chain_result, 16)
    if multicall_chain_id != CHAIN_ID:
        raise RuntimeError(f"Multicall3 getChainId() returned {multicall_chain_id}; required {CHAIN_ID}")
    return {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "rpc_endpoint": endpoint,
        "exact_command": command,
        "pinned_block": {"number": number, "hash": block_hash, "timestamp": timestamp},
        "multicall3_code_size_bytes": len(bytes.fromhex(code[2:])),
        "multicall3_code_sha256": "0x" + hashlib.sha256(bytes.fromhex(code[2:])).hexdigest(),
        "multicall3_get_chain_id": multicall_chain_id,
    }


def execute(actions, rpc_call=rpc, *, endpoint=RPC_URL, command=None):
    actions = validate_actions(actions)
    evidence = _capture_chain_evidence(rpc_call, endpoint, command or "programmatic execute()")
    block = evidence["pinned_block"]["number"]
    calldata = encode_aggregate3(actions)
    transaction = {"to": MULTICALL3, "data": calldata, "value": "0x0"}
    try:
        raw = rpc_call("eth_call", [transaction, block])
    except RPCRemoteError as exc:
        if not all(action["allow_failure"] for action in actions):
            raise AggregateRevert(str(exc), evidence) from exc
        raise
    results = decode_aggregate3(raw, len(actions))
    for index, (action, result) in enumerate(zip(actions, results)):
        if not action["allow_failure"] and not result["success"]:
            raise AggregateResultError(
                f"aggregate3 returned impossible success=false for action {index} with allow_failure=false",
                evidence,
            )
    batch_gas = _hex_quantity(rpc_call("eth_estimateGas", [transaction, block]), "batch gas estimate")
    individual_gas = []
    for action in actions:
        try:
            estimate = rpc_call("eth_estimateGas", [{"to": action["target"], "data": action["data"], "value": "0x0"}, block])
            individual_gas.append(_hex_quantity(estimate, "individual gas estimate"))
        except RPCRemoteError:
            individual_gas.append(None)
    failed = []
    for index, (action, result) in enumerate(zip(actions, results)):
        result.update({"index": index, "label": action["label"], "allow_failure": action["allow_failure"],
                       "individual_gas_estimate": individual_gas[index]})
        if not result["success"]:
            failed.append(index)
    all_individual_gas = sum(individual_gas) if all(value is not None for value in individual_gas) else None
    separate = {"action_count": len(actions), "transaction_count": len(actions), "batch_transaction_count": 1,
                "steps_saved": len(actions) - 1,
                "step_reduction_percent": round((len(actions) - 1) * 100 / len(actions), 2),
                "wording": "Comparison is against hypothetical separate transactions for these independent read calls; none were sent."}
    gas = {"batch": batch_gas, "hypothetical_separate_total": all_individual_gas,
           "difference": all_individual_gas - batch_gas if all_individual_gas is not None else None,
           "wording": "eth_estimateGas observations at one pinned block; not paid gas and not a benchmark."}
    semantics = ("Multicall3 aggregate3 executes calls in order. A failed call with allow_failure=true returns "
                 "success=false and later calls continue. A failed call with allow_failure=false reverts the entire "
                 "hypothetical transaction, rolling back every action; this tool only simulates read calls.")
    return {"status": "prepared", "network": "Pharos mainnet", "chain_id": CHAIN_ID, "multicall3": MULTICALL3,
            "evidence": evidence, "prepared_transaction": transaction, "prepared_success": True, "broadcast": False,
            "results": results, "partial_failure": {"failed_indexes": failed,
            "continued": bool(failed) and all(actions[i]["allow_failure"] for i in failed), "semantics": semantics},
            "comparison": {"hypothetical_separate_transactions": separate, "gas_estimate_observations": gas}}


def _failure(code, message, evidence=None):
    report = {"status": "failed", "exit_code": 2, "prepared_success": False, "broadcast": False,
              "error": {"code": code, "message": message}}
    if evidence is not None:
        report["evidence"] = evidence
    return report


def main(argv=None, *, rpc_call=rpc, input_loader=None, command=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("actions", help="JSON action list or @path")
    parser.add_argument("--rpc-url", default=RPC_URL)
    args = parser.parse_args(argv)
    actual_argv = list(argv) if argv is not None else sys.argv[1:]
    exact_command = command or shlex.join(["python3", "batch_executor.py", *actual_argv])
    try:
        if input_loader:
            text = input_loader(args.actions)
        elif args.actions.startswith("@"):
            with open(args.actions[1:], encoding="utf-8") as source:
                text = source.read()
        else:
            text = args.actions
        rpc_for_url = rpc_call if rpc_call is not rpc else lambda method, params: rpc(method, params, args.rpc_url)
        report = execute(json.loads(text), rpc_for_url, endpoint=args.rpc_url, command=exact_command)
    except AggregateRevert as exc:
        print(json.dumps(_failure("aggregate3_simulation_reverted", str(exc), exc.evidence), indent=2), file=sys.stderr)
        return 2
    except AggregateResultError as exc:
        print(json.dumps(_failure("aggregate3_untrusted_result", str(exc), exc.evidence), indent=2), file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError, ValueError, RPCError, RuntimeError) as exc:
        print(json.dumps(_failure("execution_failed", str(exc)), indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

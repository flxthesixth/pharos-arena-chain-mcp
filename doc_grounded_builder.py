"""Docs-first, read-only builder for three Pharos how-do-I requests."""
import argparse
import json
import re

from arena_contract_state import exchange, text
from pharos_docs import ask

ADDRESS = re.compile(r"\b0x[0-9a-fA-F]{40}\b")
SOURCE = re.compile(r"https://docs\.pharos\.xyz/[\w./-]+")
SUPPORTED = {
    "chain_id": ("chain id", "get_chain_info"),
    "block_number": ("block number", "get_block_number"),
    "balance": ("balance", "get_balance"),
}
DOC_QUESTIONS = {
    "chain_id": "How do I check Pharos network chain ID with JSON-RPC eth_chainId?",
    "block_number": "How do I get the latest Pharos block number with JSON-RPC eth_blockNumber?",
    "balance": "How do I read the native token balance of an address on Pharos with eth_getBalance?",
}


class RequestNotCovered(ValueError):
    """Request cannot be safely grounded in cited Pharos documentation."""


def chain_session():
    """Return minimal callable for hosted Chain MCP tools."""
    _, session = exchange("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                         "clientInfo": {"name": "doc-grounded-builder", "version": "1.0"}})
    if not session:
        raise RuntimeError("Chain MCP session missing")
    request_id = 1

    def call(name, arguments):
        nonlocal request_id
        request_id += 1
        result, _ = exchange("tools/call", {"name": name, "arguments": arguments}, session, request_id)
        return text(result)
    return call


def classify(request):
    lowered = request.lower()
    if "chain id" in lowered or "chainid" in lowered:
        return "chain_id"
    if "block number" in lowered or "latest block" in lowered:
        return "block_number"
    if "balance" in lowered and ADDRESS.search(request):
        return "balance"
    return None


def cited(raw):
    answer, marker, sources = raw.partition("# Sources")
    links = list(dict.fromkeys(SOURCE.findall(sources)))
    return answer.strip(), links if marker else []


class Builder:
    def __init__(self, docs_ask=ask, chain_call=None):
        self.docs_ask = docs_ask
        self.chain_call = chain_call

    def run(self, request):
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request must be non-empty text")
        kind = classify(request)
        docs_question = request if kind is None else DOC_QUESTIONS[kind]
        answer, sources = cited(self.docs_ask(docs_question))
        if kind is None:
            return {"request": request, "status": "unsupported",
                    "message": "Pharos docs have no coverage for this request; no action was improvised.",
                    "docs": {"question": docs_question, "answer": answer, "sources": sources},
                    "execution": None, "verification": {"matches_plan": False, "reason": "no supported plan"}}
        if not answer or not sources:
            raise RequestNotCovered("Docs MCP returned no cited coverage; Chain MCP was not called")

        _, tool = SUPPORTED[kind]
        arguments = {}
        checks = []
        if kind == "chain_id":
            checks = ["chainId equals hexadecimal chainIdHex", "chainIdMatches is true"]
        elif kind == "block_number":
            checks = ["blockNumber equals hexadecimal blockNumberHex", "block number is non-negative"]
        else:
            match = ADDRESS.search(request)
            if match is None:
                raise ValueError("balance request requires an EVM address")
            arguments = {"address": match.group(0), "block": "latest"}
            checks = ["returned address equals requested address", "balanceWei equals balanceHex",
                      "human PROS balance equals balanceWei at 18 decimals"]
        plan = {"docs_question": docs_question, "docs_answer": answer, "sources": sources,
                "chain_tool": tool, "arguments": arguments, "expected_checks": checks,
                "read_only": True}
        call = self.chain_call or chain_session()
        observed = call(tool, arguments)
        verified = self._verify(kind, observed, arguments)
        return {"request": request, "status": "success" if all(verified.values()) else "failure",
                "plan": plan,
                "execution": {"provider": "Chain MCP", "tool": tool, "arguments": arguments,
                              "requires_signature": False, "result": observed},
                "verification": {"matches_plan": all(verified.values()), "checks": verified}}

    @staticmethod
    def _verify(kind, value, arguments):
        if kind == "chain_id":
            return {"hex_matches_decimal": int(value["chainIdHex"], 16) == value["chainId"],
                    "configured_chain_matches": value["chainIdMatches"] is True}
        if kind == "block_number":
            number = int(value["blockNumber"])
            return {"hex_matches_decimal": int(value["blockNumberHex"], 16) == number,
                    "non_negative": number >= 0}
        wei = int(value["balanceWei"])
        rendered = str(wei // 10**18) if wei % 10**18 == 0 else f"{wei / 10**18:.18f}".rstrip("0")
        return {"address_matches": value["address"].lower() == arguments["address"].lower(),
                "hex_matches_wei": int(value["balanceHex"], 16) == wei,
                "units_match": value["balance"] == rendered and value["symbol"] == "PROS"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help='One supported read-only "How do I..." request')
    args = parser.parse_args()
    try:
        print(json.dumps(Builder().run(args.request), indent=2))
    except (OSError, ValueError, KeyError, StopIteration, RuntimeError) as exc:
        parser.exit(1, f"Builder failed: {exc}\n")


if __name__ == "__main__":
    main()

"""Read-only Pharos mainnet wallet and two USDC vault positions.

Usage: python3 pharos_portfolio_box3_20261110.py WALLET "natural-language question"
Values are raw base units. No transaction, price, or signing endpoints.
"""
import json
import re
import sys
from urllib.request import Request, urlopen

RPC = "https://rpc.pharos.xyz"
USDC = "0xC879C018dB60520F4355C26eD1a6D572cdAC1815"
VAULTS = {
    "RockawayX": "0x047cD0a91E9B92ED979189a6C8A120bf280f02E5",
    "SharpByte": "0x15c25ED222fc498f672af5c3adb5ED0a96E1AFf1",
}
NATIVE = "0x0000000000000000000000000000000000000000"  # native PROS, not a contract
QUESTIONS = ("balances", "positions", "vaults", "exposure", "compare", "largest", "earnings")
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")
WORD = re.compile(r"0x[0-9a-fA-F]{64}\Z")


def rpc(method, params):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    request = Request(RPC, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        answer = json.load(response)
    if answer.get("id") != 1 or "error" in answer or "result" not in answer:
        raise ValueError("RPC response invalid")
    return answer["result"]


def cited(value, contract, block, method):
    return {"value": str(value), "contract": contract, "block": block, "method": method}


def unknown(contract, block, method):
    return {"value": "unknown", "contract": contract, "block": block, "method": method}


def snapshot(wallet, call=rpc):
    if not ADDRESS.fullmatch(wallet):
        raise ValueError("Wallet must be 0x plus 40 hex digits")
    if call("eth_chainId", []) != "0x688":
        raise ValueError("Not Pharos mainnet")
    block_hex = call("eth_blockNumber", [])
    if not isinstance(block_hex, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", block_hex):
        raise ValueError("Invalid block")
    block = int(block_hex, 16)

    def read(contract, method, selector, argument=""):
        try:
            code = call("eth_getCode", [contract, block_hex])
            if not isinstance(code, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})+", code):
                raise ValueError("No valid contract code")
            raw = call("eth_call", [{"to": contract, "data": selector + argument}, block_hex])
            if not isinstance(raw, str) or not WORD.fullmatch(raw):
                raise ValueError("Invalid ABI word")
            return cited(int(raw, 16), contract, block, method)
        except (OSError, ValueError, TypeError, KeyError):
            return unknown(contract, block, method)

    wallet_word = wallet[2:].lower().zfill(64)
    token = read(USDC, "balanceOf(address)", "0x70a08231", wallet_word)
    try:
        native_raw = call("eth_getBalance", [wallet, block_hex])
        if not isinstance(native_raw, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", native_raw):
            raise ValueError("Invalid native balance")
        native = cited(int(native_raw, 16), NATIVE, block, "eth_getBalance (native PROS)")
    except (OSError, ValueError, TypeError, KeyError):
        native = unknown(NATIVE, block, "eth_getBalance (native PROS)")
    vaults = {}
    for name, address in VAULTS.items():
        asset = read(address, "asset()", "0x38d52e0f")
        if asset["value"] == "unknown" or int(asset["value"]) != int(USDC, 16):
            shares = unknown(address, block, "balanceOf(address)")
            underlying = unknown(address, block, "convertToAssets(uint256)")
        else:
            shares = read(address, "balanceOf(address)", "0x70a08231", wallet_word)
            underlying = (read(address, "convertToAssets(uint256)", "0x07a2d13a", format(int(shares["value"]), "064x"))
                          if shares["value"] != "unknown" else unknown(address, block, "convertToAssets(uint256)"))
        vaults[name] = {"vault": address, "asset": USDC if asset["value"] != "unknown" and int(asset["value"]) == int(USDC, 16) else "unknown",
                        "shares": shares, "underlying_usdc_raw": underlying}
    parts = [token] + [v["underlying_usdc_raw"] for v in vaults.values()]
    total = (cited(sum(int(p["value"]) for p in parts), USDC, block,
                   "sum(wallet balanceOf + vault convertToAssets); components cited separately")
             if all(p["value"] != "unknown" for p in parts)
             else unknown(USDC, block, "sum(wallet balanceOf + vault convertToAssets)"))
    return {"wallet": wallet, "block": block, "wallet_balances": {"USDC_raw": token, "PROS_wei": native},
            "vaults": vaults, "total_usdc_raw": total}


def answer(wallet, question, call=rpc):
    if not isinstance(question, str):
        raise ValueError("Question must be text")
    text = question.lower().strip()
    # ponytail: bounded question vocabulary fails closed; extend only with scoped regression tests.
    vocabulary = set(("what whats s is are am i my me do how much many in across and or the a of to please show current "
                      "wallet hold holds have assets usdc pros where which value values allocation distributed total "
                      "share shares position positions deposited deposit vault vaults protocol protocols "
                      "balance balances exposure compare comparison comparing versus vs better difference higher "
                      "biggest largest highest top most earn earned earning earnings yield apy apr return returns interest "
                      + " ".join(VAULTS).lower()).split())
    if set(re.findall(r"\w+", text)) - vocabulary:
        raise ValueError("Unsupported scope or wording; supported: wallet USDC/PROS balances and RockawayX/SharpByte USDC vaults only")
    if text in QUESTIONS:
        intent = text
    elif re.search(r"\b(earn|earned|earning|earnings|yield|apy|apr|return|returns|interest)\b", text):
        intent = "earnings"
    elif re.search(r"\b(biggest|largest|highest|top|most)\b", text):
        intent = "largest"
    elif re.search(r"\b(compar|versus|vs\b|better|difference|higher)\w*", text):
        intent = "compare"
    elif re.search(r"\b(where|exposure|total|allocation|distributed)\b", text):
        intent = "exposure"
    elif re.search(r"\b(share|shares|position|positions|deposited|deposit)\b", text):
        intent = "positions"
    elif any(re.search(r"\b" + re.escape(name.lower()) + r"\b", text) for name in VAULTS):
        intent = "positions"
    elif re.search(r"\b(vault|vaults|protocol|protocols)\b", text):
        intent = "vaults"
    elif re.search(r"\b(balance|balances|wallet|hold|have|usdc|pros)\b", text):
        intent = "balances"
    else:
        raise ValueError("Unsupported question; ask about balances, positions, vaults, exposure, comparison, largest position, or earnings/yield")
    if re.search(r"\bpros\b", text) and (intent != "balances" or
            re.search(r"\b(vault|vaults|protocol|protocols|rockawayx|sharpbyte)\b", text)):
        raise ValueError("Unsupported scope; PROS is supported only for wallet balances, not USDC vault analytics")
    state = snapshot(wallet, call)
    named = [name for name in VAULTS if re.search(r"\b" + re.escape(name.lower()) + r"\b", text)]
    wallet_requested = bool(re.search(r"\bwallet\b", text))
    vault_requested = bool(named or re.search(r"\b(vault|vaults|protocol|protocols)\b", text))
    explicit = wallet_requested or vault_requested
    vaults = {name: state["vaults"][name] for name in
              (named or VAULTS if vault_requested or not explicit and intent != "balances" else [])}
    include_wallet = wallet_requested or not explicit and intent in ("balances", "exposure", "largest")
    wallet_balances = {name: item for name, item in state["wallet_balances"].items()
                       if not re.search(r"\b(usdc|pros)\b", text) or
                       re.search(r"\b" + ("usdc" if name == "USDC_raw" else "pros") + r"\b", text)}
    values = {name: vault["underlying_usdc_raw"] for name, vault in vaults.items()}
    positions = {**({"Wallet USDC": state["wallet_balances"]["USDC_raw"]} if include_wallet else {}), **values}
    known = all(item["value"] != "unknown" for item in positions.values())
    ranked = sorted(positions, key=lambda name: int(positions[name]["value"]), reverse=True) if known else []
    largest = ranked[0] if ranked else None
    total = (cited(sum(int(item["value"]) for item in positions.values()), USDC, state["block"],
                   "sum(selected USDC positions); components cited separately") if known else
             unknown(USDC, state["block"], "sum(selected USDC positions)"))
    selected = {**({"wallet_balances": {"USDC_raw": state["wallet_balances"]["USDC_raw"]}}
                   if include_wallet else {}), **({"vaults": vaults} if vaults else {})}
    fields = {
        "balances": {"wallet_balances": wallet_balances},
        "positions": selected,
        "vaults": selected,
        "exposure": {**selected, "total_usdc_raw": total},
        "compare": {**selected, "comparison":
                    {"value": ("equal" if len({positions[name]["value"] for name in ranked}) == 1
                               else ranked[0] + "".join(
                                   (" = " if positions[left]["value"] == positions[right]["value"] else " > ") + right
                                   for left, right in zip(ranked, ranked[1:]))) if known and len(ranked) >= 2 else "unknown",
                     "unit": "USDC raw", "sources": positions,
                     "reason": None if known and len(ranked) >= 2 else "Need at least two available USDC positions"}},
        "largest": {**selected, "largest_position":
                    {"value": (largest if int(positions[largest]["value"]) > 0 else "none") if known and largest else "unknown",
                     "unit": "USDC raw", "sources": positions,
                     "reason": None if known and largest else "USDC position value unavailable"}},
        # ponytail: no historical cost basis or reward data; add yield only with cited historical reads.
        "earnings": {"earnings": {"value": "unknown", "reason": "No historical deposits, withdrawals, rewards, or cost basis; current balances cannot establish earnings or yield",
                                  "sources": positions}},
    }
    return {"wallet": wallet, "question": question, "intent": intent, "block": state["block"], **fields[intent]}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit('Usage: portfolio.py WALLET "natural-language question"')
    try:
        print(json.dumps(answer(sys.argv[1], sys.argv[2]), indent=2))
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None

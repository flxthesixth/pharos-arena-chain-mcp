"""Parse a payment request, validate it live, and emit unsigned data only."""
import argparse
from datetime import datetime, timezone
import json
import re
import shlex
import subprocess
import sys
from decimal import Decimal, InvalidOperation

RPC_URL = "https://atlantic.dplabs-internal.com"
CHAIN_ID = 688689
NETWORK = "Pharos Atlantic testnet"
EXPLORER = "https://atlantic.pharosscan.xyz"
VERSION = "1.1.0"
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
ADDRESS_LIKE = re.compile(r"0x[0-9a-fA-F]+")
AMOUNT = re.compile(r"(?<![\w.])([+-]?\d+(?:\.\d+)?)(?![\w.])")
ZERO_ADDRESS = "0x" + "0" * 40
TOKENS = {
    "USDC": ("0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8", 6),
    "USDT": ("0xE7E84B8B4f39C507499c40B4ac199B050e2882d5", 6),
    "WBTC": ("0x0c64F03EEa5c30946D5c55B4b532D08ad74638a4", 18),
    "WETH": ("0x7d211F77525ea39A0592794f793cC1036eEaccD5", 18),
    "WPHRS": ("0x838800b758277CC111B2d48Ab01e5E164f8E9471", 18),
}


class PaymentError(RuntimeError):
    pass


def is_address(value):
    return bool(re.fullmatch(r"0x[0-9a-fA-F]{40}", value or ""))


def parse_request(text):
    addresses = ADDRESS.findall(text)
    malformed = [item for item in ADDRESS_LIKE.findall(text) if not is_address(item)]
    amounts = []
    invalid_amount = False
    for raw in AMOUNT.findall(ADDRESS.sub("", text)):
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        if raw.startswith(("+", "-")) or value <= 0:
            invalid_amount = True
        elif value not in amounts:
            amounts.append(value)
    symbols = [symbol for symbol in ["PHRS", *TOKENS] if re.search(rf"(?<![A-Za-z0-9]){symbol}(?![A-Za-z0-9])", text, re.I)]
    token_contract = None
    contract_match = re.search(r"(?:token|contract)\s+(0x[0-9a-fA-F]{40})", text, re.I)
    if contract_match:
        token_contract = contract_match.group(1)
        addresses.remove(token_contract)
    questions = []
    if malformed:
        questions.append("Recipient or token address is malformed; provide 0x plus 40 hex characters.")
    if invalid_amount or len(amounts) != 1:
        questions.append("What single positive unsigned amount should be sent?")
    if ZERO_ADDRESS in [address.lower() for address in addresses]:
        questions.append("Recipient cannot be the zero address.")
    if len(addresses) != 1:
        questions.append("What single 0x-prefixed recipient address should receive payment?")
    if len(symbols) + bool(token_contract) != 1:
        questions.append("Which single token should be used: PHRS, USDC, USDT, WBTC, WETH, WPHRS, or a token contract address?")
    if questions:
        return {"status": "needs_clarification", "questions": questions, "unsigned_transaction": None}
    return {"status": "parsed", "amount": amounts[0], "token": symbols[0] if symbols else token_contract,
            "recipient": addresses[0]}


def cast(*args, runner=subprocess.run):
    result = runner(["cast", *args, "--rpc-url", RPC_URL], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise PaymentError(result.stderr.strip() or result.stdout.strip() or "cast call failed")
    return result.stdout.strip()


def as_int(output, allow_cast_annotation=False):
    value = output.strip()
    if allow_cast_annotation:
        annotated = re.fullmatch(r"([0-9]+) \[[0-9]+(?:\.[0-9]+)?e[+-]?[0-9]+\]", value, re.I)
        if annotated:
            return int(annotated.group(1))
    match = re.fullmatch(r"(?:0x([0-9a-fA-F]+)|([0-9]+))", value)
    if not match:
        raise PaymentError(f"Unexpected numeric chain response: {output!r}")
    return int(match.group(1), 16) if match.group(1) else int(match.group(2))


def units(amount, decimals):
    scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise PaymentError(f"Amount has more than {decimals} decimal places")
    return int(scaled)


def encode_transfer(recipient, raw_amount):
    return "0xa9059cbb" + recipient[2:].lower().rjust(64, "0") + hex(raw_amount)[2:].rjust(64, "0")


def prepare(text, sender, runner=subprocess.run):
    if not is_address(sender):
        raise ValueError("sender must be 0x plus 40 hex characters")
    parsed = parse_request(text)
    if parsed["status"] != "parsed":
        return parsed
    block = as_int(cast("block-number", runner=runner))
    chain_id = as_int(cast("chain-id", runner=runner))
    if chain_id != CHAIN_ID:
        raise PaymentError(f"Wrong chain ID {chain_id}; expected {CHAIN_ID}")
    token = parsed["token"]
    recipient = parsed["recipient"]
    if token == "PHRS":
        decimals, contract = 18, None
        symbol = "PHRS"
        raw_balance = as_int(cast("balance", sender, "--block", str(block), runner=runner),
                             allow_cast_annotation=True)
    else:
        contract, configured_decimals = TOKENS.get(token, (token, None))
        code = cast("code", contract, "--block", str(block), runner=runner)
        if code == "0x":
            raise PaymentError("Token address has no contract code")
        symbol = cast("call", contract, "symbol()(string)", "--block", str(block), runner=runner).strip('"')
        decimals = as_int(cast("call", contract, "decimals()(uint8)", "--block", str(block), runner=runner))
        if configured_decimals is not None and (symbol.upper() != token or decimals != configured_decimals):
            raise PaymentError("Live token metadata does not match configured token")
        raw_balance = as_int(cast("call", contract, "balanceOf(address)(uint256)", sender,
                                  "--block", str(block), runner=runner), allow_cast_annotation=True)
    raw_amount = units(parsed["amount"], decimals)
    validation_extra = {}
    required_balance = raw_amount
    if contract is not None and raw_balance < raw_amount:
        available = Decimal(raw_balance) / (Decimal(10) ** decimals)
        raise PaymentError(f"Insufficient {symbol} balance: need {parsed['amount']}, available {available}")
    if contract is None:
        estimated_gas = as_int(cast("estimate", recipient, "--from", sender, "--value", str(raw_amount),
                                    "--block", str(block), runner=runner))
        gas_limit = (estimated_gas * 12 + 9) // 10
        gas_price = as_int(cast("gas-price", runner=runner))
        maximum_fee = gas_limit * gas_price
        required_balance += maximum_fee
        validation_extra = {
            "estimated_gas": estimated_gas,
            "gas_limit": gas_limit,
            "gas_price_wei": gas_price,
            "maximum_fee_wei": maximum_fee,
            "maximum_fee_phrs": format(Decimal(maximum_fee) / (Decimal(10) ** 18), "f"),
            "required_total_wei": required_balance,
            "required_total_phrs": format(Decimal(required_balance) / (Decimal(10) ** 18), "f"),
        }
    elif cast("call", contract, "transfer(address,uint256)(bool)", recipient, str(raw_amount),
              "--from", sender, "--block", str(block), runner=runner).lower() not in ("true", "1", "0x1"):
        raise PaymentError("ERC-20 transfer simulation did not return true")
    else:
        validation_extra = {"transfer_simulation_succeeded": True}
    if raw_balance < required_balance:
        available = Decimal(raw_balance) / (Decimal(10) ** decimals)
        if contract is None:
            total = Decimal(required_balance) / (Decimal(10) ** decimals)
            raise PaymentError(f"Insufficient {symbol} balance for value plus maximum fee: need {total}, available {available}")
        raise PaymentError(f"Insufficient {symbol} balance: need {parsed['amount']}, available {available}")
    if contract is None:
        tx = {"from": sender, "to": recipient, "value": hex(raw_amount),
              "gas": hex(validation_extra["gas_limit"]),
              "gasPrice": hex(validation_extra["gas_price_wei"]), "chainId": hex(CHAIN_ID)}
    else:
        tx = {"from": sender, "to": contract, "value": "0x0", "data": encode_transfer(recipient, raw_amount),
              "chainId": hex(CHAIN_ID)}
    amount_text = format(parsed["amount"], "f")
    return {
        "status": "ready_for_wallet",
        "summary": f"Send {amount_text} {symbol} from {sender} to {recipient} on {NETWORK}.",
        "validation": {"recipient_format": "valid", "token_contract": contract,
                       "token_contract_code_and_metadata_valid": True if contract else None,
                       "symbol": symbol, "decimals": decimals,
                       "sender_balance": format(Decimal(raw_balance) / (Decimal(10) ** decimals), "f"),
                       "sufficient_balance": True, "block": block, "chain_id": chain_id,
                       "sender_explorer": f"{EXPLORER}/address/{sender}",
                       "recipient_explorer": f"{EXPLORER}/address/{recipient}", **validation_extra},
        "unsigned_transaction": tx,
        "wallet_request": {"method": "eth_sendTransaction", "params": [tx]},
        "safety": {"signed": False, "broadcast": False, "private_key_requested": False,
                   "user_wallet_confirmation_required": True},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="Free-text payment request")
    parser.add_argument("--from", dest="sender", required=True, help="Sender public address; never a private key")
    args = parser.parse_args()
    try:
        report = prepare(args.request, args.sender)
        report["evidence"] = {
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "command": shlex.join(["python3", *sys.argv]),
            "rpc_endpoint": RPC_URL,
            "fixed_block": report.get("validation", {}).get("block"),
            "source_mode": "live_rpc",
            "source_version": VERSION,
        }
        print(json.dumps(report, indent=2, default=str))
    except (ValueError, PaymentError) as error:
        print(json.dumps({"status": "rejected", "error": str(error), "unsigned_transaction": None}, indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()

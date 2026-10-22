"""Validate invoices and build unsigned Atlantic PHRS payment payloads."""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.request import Request, urlopen

CHAIN_ID = 688689
RPC_URL = "https://atlantic.dplabs-internal.com"
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
AMOUNT = re.compile(r"^[0-9]+(?:\.[0-9]+)?$")
TEXT_FIELDS = {
    "payee": re.compile(r"^Pay to:\s*(.+)$", re.I),
    "total": re.compile(r"^Total:\s*(\S+)\s+(\S+)\s*$", re.I),
    "reference": re.compile(r"^Reference:\s*(.+)$", re.I),
}
REQUIRED = ("payee", "amount", "currency", "reference")


class InvoiceError(ValueError):
    pass


def _single(values, field):
    if not values:
        raise InvoiceError(f"missing field: {field}")
    if len(set(values)) != 1:
        raise InvoiceError(f"mismatch: conflicting {field} values")
    return values[0]


def parse_json_invoice(text):
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value and value[key] != item:
                raise InvoiceError(f"mismatch: conflicting {key} values")
            value[key] = item
        return value

    try:
        value = json.loads(text, object_pairs_hook=unique_object)
    except json.JSONDecodeError as error:
        raise InvoiceError(f"invalid JSON: {error.msg}") from error
    if not isinstance(value, dict):
        raise InvoiceError("JSON invoice must be an object")
    unknown = set(value) - set(REQUIRED)
    if unknown:
        raise InvoiceError("unknown fields: " + ", ".join(sorted(unknown)))
    missing = [field for field in REQUIRED if field not in value or value[field] in (None, "")]
    if missing:
        raise InvoiceError("missing fields: " + ", ".join(missing))
    return {field: str(value[field]) for field in REQUIRED}


def parse_text_invoice(text):
    found = {field: [] for field in ("payee", "total", "reference")}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.upper() == "INVOICE":
            continue
        matched = False
        for field, pattern in TEXT_FIELDS.items():
            match = pattern.fullmatch(line)
            if match:
                found[field].append(match.groups())
                matched = True
                break
        if not matched:
            raise InvoiceError(f"unrecognized invoice line: {line}")
    payee = _single([parts[0] for parts in found["payee"]], "payee")
    total = _single(found["total"], "total")
    reference = _single([parts[0] for parts in found["reference"]], "reference")
    return {"payee": payee, "amount": total[0], "currency": total[1], "reference": reference}


def parse_invoice(text, invoice_format):
    if invoice_format == "auto":
        invoice_format = "json" if text.lstrip().startswith(("{", "[")) else "text"
    parser = parse_json_invoice if invoice_format == "json" else parse_text_invoice
    return parser(text), invoice_format


def validate_invoice(invoice):
    errors = []
    payee = invoice.get("payee", "")
    if not ADDRESS.fullmatch(payee):
        errors.append("payee must be a 0x-prefixed 20-byte address")
    elif int(payee, 16) == 0:
        errors.append("payee must not be the zero address")
    amount_text = invoice.get("amount", "")
    if not AMOUNT.fullmatch(amount_text):
        errors.append("amount must be a positive plain decimal")
        amount = None
    else:
        try:
            amount = Decimal(amount_text)
            if amount <= 0:
                errors.append("amount must be greater than zero")
            exponent = amount.as_tuple().exponent
            if isinstance(exponent, int) and max(0, -exponent) > 18:
                errors.append("amount exceeds PHRS 18-decimal precision")
        except InvalidOperation:
            amount = None
            errors.append("amount must be a positive plain decimal")
    if invoice.get("currency") != "PHRS":
        errors.append("currency must be PHRS; ERC-20 transfer calldata cannot carry an invoice reference")
    reference = invoice.get("reference", "")
    if not reference.strip():
        errors.append("reference must not be blank")
    elif len(reference.encode("utf-8")) > 128:
        errors.append("reference exceeds 128 UTF-8 bytes")
    if errors:
        raise InvoiceError("; ".join(errors))
    return amount


def reconcile(invoice, expected):
    if expected is None:
        return
    missing = [field for field in REQUIRED if field not in expected]
    if missing:
        raise InvoiceError("expected record missing fields: " + ", ".join(missing))
    mismatches = []
    for field in REQUIRED:
        left, right = str(invoice[field]), str(expected[field])
        if field == "payee":
            equal = left.lower() == right.lower()
        elif field == "amount":
            try:
                equal = Decimal(left) == Decimal(right)
            except InvalidOperation:
                equal = False
        else:
            equal = left == right
        if not equal:
            mismatches.append(field)
    if mismatches:
        raise InvoiceError("mismatch against expected record: " + ", ".join(mismatches))


def rpc_call(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = Request(RPC_URL, body, {"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=20) as response:
        reply = json.load(response)
    if "error" in reply:
        raise InvoiceError(f"Atlantic RPC error: {reply['error'].get('message', reply['error'])}")
    return reply.get("result")


def rpc_code(address):
    chain_id = rpc_call("eth_chainId", [])
    if (not isinstance(chain_id, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", chain_id)
            or int(chain_id, 16) != CHAIN_ID):
        raise InvoiceError(f"Atlantic RPC chain ID mismatch: expected {CHAIN_ID}, got {chain_id!r}")
    block_number = rpc_call("eth_blockNumber", [])
    if not isinstance(block_number, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", block_number):
        raise InvoiceError("Atlantic RPC returned invalid eth_blockNumber result")
    code = rpc_call("eth_getCode", [address, block_number])
    if not isinstance(code, str) or not re.fullmatch(r"0x[0-9a-fA-F]*", code):
        raise InvoiceError("Atlantic RPC returned invalid eth_getCode result")
    block = rpc_call("eth_getBlockByNumber", [block_number, False])
    timestamp = block.get("timestamp") if isinstance(block, dict) else None
    if not isinstance(timestamp, str) or not re.fullmatch(r"0x[0-9a-fA-F]+", timestamp):
        raise InvoiceError("Atlantic RPC returned invalid block timestamp")
    return {"block_number": block_number, "block_timestamp": timestamp, "code": code}


def build(invoice, invoice_format, expected=None, code_lookup=rpc_code):
    amount = validate_invoice(invoice)
    assert amount is not None
    reconcile(invoice, expected)
    snapshot = code_lookup(invoice["payee"])
    code = snapshot["code"]
    if code != "0x" and int(code, 16) != 0:
        raise InvoiceError("payee has deployed code; reference calldata semantics are not verified")
    block_number = snapshot["block_number"]
    block_timestamp = snapshot["block_timestamp"]
    whole, _, fraction = invoice["amount"].partition(".")
    amount_wei = int(whole) * 10**18 + int(fraction.ljust(18, "0") or "0")
    data = "0x" + invoice["reference"].encode("utf-8").hex()
    return {
        "status": "ready",
        "network": {"name": "Pharos Atlantic Testnet", "chain_id": CHAIN_ID},
        "invoice": {**invoice, "format": invoice_format},
        "validation": {"fields_complete": True,
                       "expected_record": {"checked": expected is not None,
                                           "match": True if expected is not None else None},
                       "code_at_block": "empty", "payee_code": code},
        "provenance": {
            "rpc_endpoint": RPC_URL,
            "network": "Pharos Atlantic Testnet",
            "chain_id": CHAIN_ID,
            "block_number": block_number,
            "block_timestamp": block_timestamp,
            "block_timestamp_utc": datetime.fromtimestamp(int(block_timestamp, 16), timezone.utc).isoformat(),
            "reproduction_command": (
                f"cast code {invoice['payee']} --block {block_number} --rpc-url {RPC_URL}"
                "  # eth_getCode pinned to exact block"
            ),
        },
        "payment_summary": {"payee": invoice["payee"], "amount": invoice["amount"],
                            "currency": "PHRS", "amount_wei": str(amount_wei),
                            "reference": invoice["reference"]},
        "unsigned_transaction": {"chainId": hex(CHAIN_ID), "to": invoice["payee"],
                                 "value": hex(amount_wei), "data": data},
        "execution": {"signed": False, "broadcast": False},
    }


def process(text, invoice_format="auto", expected=None, code_lookup=rpc_code):
    try:
        invoice, detected = parse_invoice(text, invoice_format)
        return build(invoice, detected, expected, code_lookup)
    except (InvoiceError, OSError) as error:
        return {"status": "blocked", "errors": [str(error)],
                "unsigned_transaction": None,
                "execution": {"signed": False, "broadcast": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("invoice", help="invoice path")
    parser.add_argument("--format", choices=("auto", "json", "text"), default="auto")
    parser.add_argument("--expect", help="JSON expected-record path")
    args = parser.parse_args()
    with open(args.invoice, encoding="utf-8") as source:
        text = source.read()
    expected = None
    if args.expect:
        with open(args.expect, encoding="utf-8") as source:
            expected = json.load(source)
    report = process(text, args.format, expected)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ready" else 2


if __name__ == "__main__":
    sys.exit(main())

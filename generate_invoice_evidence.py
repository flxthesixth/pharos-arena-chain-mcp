"""Regenerate Invoice-to-Payment evidence with stdlib only."""
import json
from pathlib import Path

import invoice_payment_agent as agent


ROOT = Path(__file__).resolve().parent
INVOICE = json.loads((ROOT / "samples/invoice.json").read_text(encoding="utf-8"))
EXPECTED = json.loads((ROOT / "samples/expected.json").read_text(encoding="utf-8"))
TEXT = (ROOT / "samples/invoice.txt").read_text(encoding="utf-8")


def wrong_chain(_method, _params):
    return "0x1"


def main():
    missing = dict(INVOICE)
    missing.pop("reference")
    expected_amount = dict(EXPECTED, amount="99")
    expected_reference = dict(EXPECTED, reference="WRONG")
    zero_address = dict(INVOICE, payee="0x" + "0" * 40)

    evidence = {
        "generation_command": "python3 generate_invoice_evidence.py",
        "json_success": agent.process(json.dumps(INVOICE), expected=EXPECTED),
        "text_success": agent.process(TEXT),
        "missing_field": agent.process(json.dumps(missing)),
        "json_expected_mismatch": agent.process(json.dumps(INVOICE), expected=expected_amount),
        "text_expected_mismatch": agent.process(TEXT, expected=expected_reference),
        "zero_address": agent.process(json.dumps(zero_address)),
    }
    original_rpc_call = agent.rpc_call
    try:
        agent.rpc_call = wrong_chain
        evidence["chain_id_mismatch"] = agent.process(json.dumps(INVOICE))
    finally:
        agent.rpc_call = original_rpc_call

    output = ROOT / "evidence/invoice-to-payment-agent.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()

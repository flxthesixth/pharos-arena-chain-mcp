import json
import unittest
from unittest.mock import call, patch

import invoice_payment_agent as subject


PAYEE = "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
INVOICE = {"payee": PAYEE, "amount": "0.025", "currency": "PHRS", "reference": "ATL-INV-2026-001"}


def snapshot(_):
    return {"block_number": "0x123", "block_timestamp": "0x654321", "code": "0x"}


class InvoicePaymentAgentTests(unittest.TestCase):
    def test_rpc_code_pins_code_lookup_to_resolved_block(self):
        replies = [hex(subject.CHAIN_ID), "0x123", "0x", {"timestamp": "0x654321"}]
        with patch.object(subject, "rpc_call", side_effect=replies) as rpc:
            self.assertEqual(snapshot(None), subject.rpc_code(PAYEE))
        self.assertEqual(
            [
                call("eth_chainId", []),
                call("eth_blockNumber", []),
                call("eth_getCode", [PAYEE, "0x123"]),
                call("eth_getBlockByNumber", ["0x123", False]),
            ],
            rpc.call_args_list,
        )

    def test_rpc_code_rejects_wrong_chain_before_block_or_code_lookup(self):
        with patch.object(subject, "rpc_call", return_value="0x1") as rpc:
            with self.assertRaisesRegex(subject.InvoiceError, "expected 688689"):
                subject.rpc_code(PAYEE)
        rpc.assert_called_once_with("eth_chainId", [])

    def test_json_builds_unsigned_native_payment_with_reference_data(self):
        report = subject.process(json.dumps(INVOICE), expected=INVOICE, code_lookup=snapshot)
        self.assertEqual("ready", report["status"])
        self.assertEqual("json", report["invoice"]["format"])
        self.assertEqual(hex(25_000_000_000_000_000), report["unsigned_transaction"]["value"])
        self.assertEqual("0x" + INVOICE["reference"].encode().hex(), report["unsigned_transaction"]["data"])
        self.assertFalse(report["execution"]["signed"])
        self.assertFalse(report["execution"]["broadcast"])
        self.assertEqual({"checked": True, "match": True}, report["validation"]["expected_record"])
        self.assertEqual("empty", report["validation"]["code_at_block"])
        self.assertNotIn("payee_type", report["validation"])
        self.assertEqual("0x123", report["provenance"]["block_number"])
        self.assertEqual("0x654321", report["provenance"]["block_timestamp"])
        self.assertIn("eth_getCode", report["provenance"]["reproduction_command"])
        self.assertIn("0x123", report["provenance"]["reproduction_command"])

    def test_text_format(self):
        text = f"INVOICE\nPay to: {PAYEE}\nTotal: 1.5 PHRS\nReference: ATL-INV-2026-002\n"
        report = subject.process(text, code_lookup=snapshot)
        self.assertEqual("ready", report["status"])
        self.assertEqual("text", report["invoice"]["format"])
        self.assertEqual("0x14d1120d7b160000", report["unsigned_transaction"]["value"])
        self.assertEqual({"checked": False, "match": None}, report["validation"]["expected_record"])

    def test_missing_field_blocks_without_transaction(self):
        broken = dict(INVOICE)
        del broken["reference"]
        report = subject.process(json.dumps(broken), code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("missing fields: reference", report["errors"][0])
        self.assertIsNone(report["unsigned_transaction"])

    def test_zero_address_blocks_before_rpc(self):
        zero_address = "0x" + "0" * 40
        with patch.object(subject, "rpc_code") as rpc:
            report = subject.process(json.dumps(dict(INVOICE, payee=zero_address)))
        self.assertEqual("blocked", report["status"])
        self.assertIn("zero address", report["errors"][0])
        rpc.assert_not_called()

    def test_duplicate_text_field_mismatch_blocks(self):
        text = f"Pay to: {PAYEE}\nTotal: 1 PHRS\nTotal: 2 PHRS\nReference: INV-1"
        report = subject.process(text, code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("conflicting total values", report["errors"][0])

    def test_duplicate_json_field_mismatch_blocks(self):
        text = '{"payee":"%s","amount":"1","amount":"2","currency":"PHRS","reference":"INV-1"}' % PAYEE
        report = subject.process(text, code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("conflicting amount values", report["errors"][0])

    def test_json_expected_record_mismatch_blocks(self):
        expected = dict(INVOICE, amount="99")
        report = subject.process(json.dumps(INVOICE), expected=expected, code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("amount", report["errors"][0])

    def test_text_expected_record_mismatch_blocks(self):
        text = f"Pay to: {PAYEE}\nTotal: 0.025 PHRS\nReference: WRONG"
        report = subject.process(text, expected=INVOICE, code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("reference", report["errors"][0])

    def test_erc20_is_rejected_not_faked(self):
        erc20 = dict(INVOICE, currency="USDC")
        report = subject.process(json.dumps(erc20), code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("ERC-20 transfer calldata cannot carry", report["errors"][0])

    def test_contract_payee_rejected_without_verified_semantics(self):
        report = subject.process(
            json.dumps(INVOICE),
            code_lookup=lambda _: {"block_number": "0x123", "block_timestamp": "0x654321", "code": "0x6000"},
        )
        self.assertEqual("blocked", report["status"])
        self.assertIn("reference calldata semantics are not verified", report["errors"][0])

    def test_fraction_beyond_18_decimals_is_rejected(self):
        report = subject.process(json.dumps(dict(INVOICE, amount="0.0000000000000000001")), code_lookup=snapshot)
        self.assertEqual("blocked", report["status"])
        self.assertIn("18-decimal precision", report["errors"][0])


if __name__ == "__main__":
    unittest.main()

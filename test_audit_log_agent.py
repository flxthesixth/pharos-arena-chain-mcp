import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import audit_log_agent as agent

WALLET = "0x1111111111111111111111111111111111111111"
OTHER = "0x2222222222222222222222222222222222222222"
CONTRACT = "0x3333333333333333333333333333333333333333"


class AuditLogAgentTests(unittest.TestCase):
    def test_inputs_reject_bad_address_and_reversed_range(self):
        with self.assertRaisesRegex(ValueError, "wallet"):
            agent.validate_wallet("0x123")
        with self.assertRaisesRegex(ValueError, "start"):
            agent.parse_range("2026-01-02", "2026-01-01")

    def test_date_only_range_is_inclusive_utc_day(self):
        start, end = agent.parse_range("2026-01-01", "2026-01-01")
        self.assertEqual(start, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2026, 1, 2, tzinfo=timezone.utc))

    def test_classifies_all_required_categories_deterministically(self):
        txs = [
            {"hash": "0x01", "from": OTHER, "to": WALLET, "value": "0x5", "input": "0x", "blockNumber": "0xa", "transactionIndex": "0x0"},
            {"hash": "0x02", "from": WALLET, "to": OTHER, "value": "0x7", "input": "0x", "blockNumber": "0xa", "transactionIndex": "0x1"},
            {"hash": "0x03", "from": WALLET, "to": CONTRACT, "value": "0x0", "input": "0x38ed1739abcd", "blockNumber": "0xa", "transactionIndex": "0x2"},
            {"hash": "0x04", "from": WALLET, "to": CONTRACT, "value": "0x0", "input": "0xdeadbeef", "blockNumber": "0xa", "transactionIndex": "0x3"},
        ]
        logs = [
            {"kind": "approval", "transactionHash": "0x05", "blockNumber": "0xa", "logIndex": "0x0", "address": CONTRACT,
             "topics": [agent.APPROVAL_TOPIC, agent.address_topic(WALLET), agent.address_topic(OTHER)], "data": "0x" + "0" * 63 + "9"},
            {"kind": "transfer_in", "transactionHash": "0x06", "blockNumber": "0xa", "logIndex": "0x1", "address": CONTRACT,
             "topics": [agent.TRANSFER_TOPIC, agent.address_topic(OTHER), agent.address_topic(WALLET)], "data": "0x" + "0" * 63 + "b"},
            {"kind": "transfer_out", "transactionHash": "0x07", "blockNumber": "0xa", "logIndex": "0x2", "address": CONTRACT,
             "topics": [agent.TRANSFER_TOPIC, agent.address_topic(WALLET), agent.address_topic(OTHER)], "data": "0x" + "0" * 63 + "d"},
        ]
        records = agent.classify(WALLET, txs, logs, {10: 1_767_225_600})
        self.assertEqual([r["category"] for r in records], [
            "transfers_in", "approvals", "transfers_in", "transfers_out",
            "transfers_out", "swaps", "contract_interactions",
        ])
        report = agent.build_report(WALLET, "2026-01-01", "2026-01-01", 10, 10, records, "2026-01-02T00:00:00+00:00")
        self.assertEqual(report["totals"]["transfers_in"], {"count": 2, "amounts_raw": {"PROS": "5", CONTRACT: "11"}})
        self.assertEqual(report["totals"]["transfers_out"]["count"], 2)
        self.assertEqual(report["totals"]["swaps"]["count"], 1)
        self.assertEqual(report["totals"]["approvals"]["count"], 1)
        self.assertEqual(report["totals"]["contract_interactions"]["count"], 1)
        self.assertTrue(all(item["explorer_url"].endswith(item["tx_hash"]) for item in report["notable_transactions"]))

    def test_markdown_export_contains_totals_and_links(self):
        record = {"category": "transfers_in", "tx_hash": "0xabc", "block": 10,
                  "timestamp": "2026-01-01T00:00:00+00:00", "asset": "PROS", "amount_raw": "5",
                  "counterparty": OTHER, "explorer_url": agent.EXPLORER + "/tx/0xabc"}
        report = agent.build_report(WALLET, "2026-01-01", "2026-01-01", 10, 10, [record], "2026-01-02T00:00:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.md"
            agent.export_markdown(report, output)
            text = output.read_text()
        self.assertIn("# Pharos Wallet Audit Log", text)
        self.assertIn("| Transfers in | 1 |", text)
        self.assertIn("[0xabc]", text)
        self.assertIn("Chain MCP", text)


if __name__ == "__main__":
    unittest.main()

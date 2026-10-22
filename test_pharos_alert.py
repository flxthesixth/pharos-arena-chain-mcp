import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

import pharos_alert


EVENT = {
    "amount": "125.5",
    "from": "0x" + "1" * 40,
    "to": "0x" + "2" * 40,
    "block": 7,
    "tx_hash": "0xabc",
    "log_index": 3,
    "symbol": "USDC",
}


class Response:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class AlertTests(unittest.TestCase):
    def test_threshold_and_content(self):
        sent = []
        receipt = pharos_alert.alert(EVENT, Decimal("100"), lambda text: sent.append(text) or {"message_id": 9})
        self.assertEqual(receipt, {"message_id": 9})
        self.assertIn("USDC Transfer", sent[0])
        self.assertIn("125.5 USDC", sent[0])
        self.assertIn("https://www.pharosscan.xyz/tx/0xabc", sent[0])
        self.assertIsNone(pharos_alert.alert(EVENT, Decimal("126"), sent.append))
        self.assertEqual(len(sent), 1)

    def test_telegram_validates_api_and_returns_sanitized_receipt(self):
        payload = {"ok": True, "result": {"message_id": 42, "date": 1700000000,
                                             "chat": {"id": -1001234567890}, "text": "hello"}}
        opener = lambda request, timeout: Response(payload)
        receipt = pharos_alert.telegram_sender("secret-token", "-1001234567890", opener=opener)("hello")
        self.assertEqual(receipt["platform"], "telegram")
        self.assertEqual(receipt["message_id"], 42)
        self.assertEqual(receipt["chat_id"], "**********7890")
        self.assertTrue(receipt["http_success"])
        self.assertTrue(receipt["api_success"])
        self.assertTrue(receipt["response_chat_matches"])
        self.assertTrue(receipt["response_text_matches"])
        self.assertEqual(receipt["content_sha256"],
                         "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824")
        self.assertIn("T", receipt["delivered_at"])
        self.assertNotIn("secret-token", json.dumps(receipt))

    def test_telegram_rejects_http_and_api_errors_without_secret(self):
        def http_error(request, timeout):
            raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)
        for opener in (http_error, lambda request, timeout: Response({"ok": False, "description": "bad token"})):
            with self.subTest(opener=opener), self.assertRaises(pharos_alert.DeliveryError) as caught:
                pharos_alert.telegram_sender("secret-token", "123", opener=opener)("hello")
            self.assertNotIn("secret-token", str(caught.exception))

    def test_duplicate_suppression_uses_durable_event_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = pharos_alert.new_state(7)
            event_id = pharos_alert.event_id(EVENT)
            state["outbox"][event_id] = {"status": "pending"}
            pharos_alert.save(path, state)
            sent = []
            with patch.object(pharos_alert, "tool", side_effect=self.fake_tool):
                self.assertEqual(pharos_alert.process("s", state, path, Decimal("100"), sent.append), 0)
            self.assertEqual(sent, [])
            persisted = json.loads(path.read_text())
            self.assertEqual(persisted["outbox"][event_id]["status"], "pending")

    def test_ambiguous_failure_persists_across_restart_and_never_auto_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = pharos_alert.new_state(7)
            attempts = []
            def fail(text):
                attempts.append(text)
                raise TimeoutError("response lost after possible acceptance")
            with patch.object(pharos_alert, "tool", side_effect=self.fake_tool):
                with self.assertRaises(TimeoutError):
                    pharos_alert.process("s", state, path, Decimal("100"), fail)
                reloaded = pharos_alert.load_state(path)
                record = reloaded["outbox"][pharos_alert.event_id(EVENT)]
                self.assertEqual(record["status"], "delivery_uncertain")
                self.assertTrue(record["manual_reconciliation_required"])
                self.assertEqual(record["error_type"], "TimeoutError")
                count = pharos_alert.process(
                    "s", reloaded, path, Decimal("100"),
                    lambda _text: self.fail("ambiguous event retried after restart"),
                )
            self.assertEqual(count, 0)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(pharos_alert.load_state(path)["outbox"][pharos_alert.event_id(EVENT)]["status"],
                             "delivery_uncertain")

    def test_success_persists_delivery_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = pharos_alert.new_state(7)
            receipt = {"platform": "telegram", "message_id": 8, "delivered_at": "2026-01-01T00:00:00Z",
                       "http_success": True, "api_success": True, "chat_id": "***1234"}
            with patch.object(pharos_alert, "tool", side_effect=self.fake_tool):
                count = pharos_alert.process("s", state, path, Decimal("100"), lambda text: receipt)
            self.assertEqual(count, 1)
            reloaded = pharos_alert.load_state(path)
            record = reloaded["outbox"][pharos_alert.event_id(EVENT)]
            self.assertEqual(record["status"], "delivered")
            self.assertEqual(record["receipt"], receipt)
            self.assertEqual(reloaded["cursor"], {"block": 8, "log_index": -1})

    @staticmethod
    def fake_tool(name, arguments, session):
        if name == "get_block_number":
            return {"blockNumber": 7}
        raw = {
            "topics": [pharos_alert.TRANSFER, "0x" + "0" * 24 + "1" * 40, "0x" + "0" * 24 + "2" * 40],
            "data": hex(125500000), "blockNumber": "0x7", "transactionHash": "0xabc", "logIndex": "0x3",
        }
        return {"logs": [raw]}


if __name__ == "__main__":
    unittest.main()

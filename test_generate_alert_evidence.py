import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_alert_evidence


EVENT = {
    "amount": "125.5", "from": "0x" + "1" * 40, "to": "0x" + "2" * 40,
    "block": 7, "tx_hash": "0x" + "a" * 64, "log_index": 3, "symbol": "USDC",
}


class EvidenceTests(unittest.TestCase):
    def test_sends_one_labeled_alert_and_writes_sanitized_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            event_path, state_path, evidence_path = root / "event.json", root / "state.json", root / "evidence.json"
            event_path.write_text(json.dumps(EVENT))
            sent = []
            receipt = {"platform": "telegram", "chat_id": "********7890", "message_id": 42,
                       "delivered_at": "2026-01-01T00:00:00Z", "http_success": True, "api_success": True}
            with patch.object(generate_alert_evidence, "configured_sender", return_value=lambda text: sent.append(text) or receipt):
                result = generate_alert_evidence.run(event_path, state_path, evidence_path)
            self.assertIn("ARENA DEMO", sent[0])
            self.assertEqual(len(sent), 1)
            self.assertEqual(result["receipt"], receipt)
            evidence = evidence_path.read_text()
            self.assertNotIn("token", evidence.lower())
            self.assertNotIn(EVENT["from"], evidence)
            with self.assertRaises(RuntimeError):
                generate_alert_evidence.run(event_path, state_path, evidence_path)
            self.assertEqual(len(sent), 1)

    def test_rejects_non_public_event_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps({**EVENT, "tx_hash": "0xabc"}))
            with self.assertRaises(ValueError):
                generate_alert_evidence.run(path, Path(directory) / "state.json", Path(directory) / "out.json")


if __name__ == "__main__":
    unittest.main()

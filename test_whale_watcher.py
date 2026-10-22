import json
import tempfile
import unittest
from pathlib import Path

import whale_watcher as subject


A = ["0x" + str(i) * 40 for i in range(1, 6)]
TOKEN = "0x" + "a" * 40
TX = "0x" + "b" * 64


def config():
    return {"network": {"name": "Pharos mainnet", "chain_id": 1672, "explorer": "https://www.pharosscan.xyz"},
            "lookback_blocks": 100, "tokens": {TOKEN: {"symbol": "USDC", "decimals": 6, "significant_threshold": "1000"}},
            "watched_addresses": dict(zip(A, [f"whale {i}" for i in range(1, 6)])),
            "known_labels": {"0x" + "f" * 40: "known venue"}}


class WhaleWatcherTests(unittest.TestCase):
    def test_complete_report_labels_flags_summarizes_and_links(self):
        calls = []
        log = {"topics": [subject.TRANSFER, subject.address_topic(A[0]), subject.address_topic("0x" + "f" * 40)],
               "data": hex(1_500_000_000), "blockNumber": "0x64", "transactionHash": TX, "logIndex": "0x2"}

        def call(name, args):
            calls.append((name, args))
            if name == "get_chain_info":
                return {"chainId": 1672, "chainIdMatches": True, "latestBlock": 100, "latestBlockHex": "0x64"}
            return {"logs": [log] if args["topics"][1] is not None else []}

        report = subject.build_report(config(), call, "2026-01-01T00:00:00+00:00")
        self.assertEqual(5, report["configuration"]["watched_address_count"])
        self.assertEqual(1, report["summary"]["transfer_count"])
        self.assertEqual(1, report["summary"]["significant_transfer_count"])
        move = report["significant_moves"][0]
        self.assertEqual("1500", move["amount"])
        self.assertEqual("known venue", move["to"]["label"])
        self.assertIn("1500 USDC moved from whale 1 to known venue", move["explanation"])
        self.assertEqual(f"https://www.pharosscan.xyz/tx/{TX}", move["explorer_url"])
        self.assertEqual("1500", report["summary"]["by_address"][A[0]]["sent"])
        self.assertTrue(all(name in ("get_chain_info", "get_logs") for name, _ in calls))

    def test_deduplicates_self_transfer_from_two_indexed_queries(self):
        log = {"topics": [subject.TRANSFER, subject.address_topic(A[0]), subject.address_topic(A[0])],
               "data": hex(1), "blockNumber": "0x64", "transactionHash": TX, "logIndex": "0x0"}
        def call(name, args):
            return ({"chainId": 1672, "chainIdMatches": True, "latestBlock": 100, "latestBlockHex": "0x64"}
                    if name == "get_chain_info" else {"logs": [log]})
        self.assertEqual(1, subject.build_report(config(), call)["summary"]["transfer_count"])

    def test_rejects_fewer_than_five_addresses(self):
        bad = config()
        bad["watched_addresses"].pop(A[-1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "at least 5"):
                subject.load_config(path)

    def test_rejects_wrong_chain(self):
        with self.assertRaisesRegex(RuntimeError, "chain mismatch"):
            subject.build_report(config(), lambda *_: {"chainId": 1, "chainIdMatches": False})


if __name__ == "__main__":
    unittest.main()

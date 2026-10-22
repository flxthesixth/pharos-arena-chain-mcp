import unittest

from wallet_risk_checker import analyze, normalize_address, validate_block


CLEAN = "0xb02627392ff222e997370e0d1d2ab6b846d76b59"
RISKY = "0x013de7ba7ebd8d186bebf4f08fbd229dfb362906"
FLAGGED = "0x9999999999999999999999999999999999999999"


class WalletRiskCheckerTests(unittest.TestCase):
    def test_rejects_invalid_address(self):
        with self.assertRaisesRegex(ValueError, "0x-prefixed 20-byte"):
            normalize_address("not-an-address")

    def test_rejects_future_snapshot_block(self):
        with self.assertRaisesRegex(ValueError, "latest block"):
            validate_block(101, 100)
        self.assertEqual(validate_block(99, 100), 99)

    def test_clean_active_eoa_is_low_with_five_explained_signals(self):
        report = analyze(CLEAN, {
            "balance_wei": 10**18, "nonce": 8, "code": "0x",
            "incoming": 1, "outgoing": 2, "approval_count": 0,
            "unique_spenders": 0, "flagged_interactions": [],
            "window_from": 900, "window_to": 1000,
        })
        self.assertEqual(report["risk_level"], "low")
        self.assertEqual(report["score"], 0)
        self.assertGreaterEqual(len(report["signals"]), 5)
        self.assertTrue(all(item["plain_language"] for item in report["signals"]))
        self.assertTrue(any("No risk rules fired" in reason for reason in report["reasons"]))

    def test_freshly_funded_low_activity_eoa_is_high(self):
        report = analyze(RISKY, {
            "balance_wei": 7 * 10**18, "nonce": 0, "code": "0x",
            "incoming": 1, "outgoing": 0, "approval_count": 0,
            "unique_spenders": 0, "flagged_interactions": [],
            "window_from": 900, "window_to": 1000,
        })
        self.assertEqual(report["risk_level"], "high")
        self.assertEqual(report["score"], 3)
        self.assertTrue(any("freshly funded" in reason.lower() for reason in report["reasons"]))
        self.assertTrue(any("outgoing transaction" in reason.lower() for reason in report["reasons"]))

    def test_flagged_interaction_and_unusual_approvals_are_specific(self):
        report = analyze(CLEAN, {
            "balance_wei": 1, "nonce": 9, "code": "0x",
            "incoming": 0, "outgoing": 1, "approval_count": 5,
            "unique_spenders": 3, "flagged_interactions": [FLAGGED],
            "window_from": 1, "window_to": 10,
        })
        self.assertEqual(report["risk_level"], "high")
        text = " ".join(report["reasons"])
        self.assertIn(FLAGGED, text)
        self.assertIn("5 approval", text)
        self.assertIn("3 spenders", text)

    def test_contract_is_not_called_freshly_funded(self):
        report = analyze(CLEAN, {
            "balance_wei": 1, "nonce": 0, "code": "0x6000",
            "incoming": 1, "outgoing": 0, "approval_count": 0,
            "unique_spenders": 0, "flagged_interactions": [],
            "window_from": 1, "window_to": 2,
        })
        self.assertFalse(any("freshly funded" in reason.lower() for reason in report["reasons"]))


if __name__ == "__main__":
    unittest.main()

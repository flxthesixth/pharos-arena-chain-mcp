"""Run: python3 -m unittest discover -p 'test_pharos_portfolio_box3_20261110.py' -v"""
import unittest
from pharos_portfolio_box3_20261110 import USDC, VAULTS, answer

WALLET = "0x" + "ab" * 20
BLOCK = "0x1596266"


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.seen = []

    def fake(self, method, params):
        self.seen.append((method, params))
        if method == "eth_chainId":
            return "0x688"
        if method == "eth_blockNumber":
            return BLOCK
        self.assertEqual(params[-1], BLOCK)
        if method == "eth_getCode":
            return "0x6001"
        if method == "eth_getBalance":
            return "0x7"
        self.assertEqual(method, "eth_call")
        address, data = params[0]["to"], params[0]["data"]
        if data == "0x38d52e0f":
            return "0x" + format(int(USDC, 16), "064x")
        if data.startswith("0x70a08231"):
            self.assertEqual(data[10:], WALLET[2:].zfill(64))
            return "0x" + format(3 if address == USDC else 5, "064x")
        self.assertEqual(data, "0x07a2d13a" + format(5, "064x"))
        return "0x" + format(9 if address == VAULTS["RockawayX"] else 12, "064x")

    def broken(self, method, params):
        if method == "eth_call" and params[0]["to"] == VAULTS["RockawayX"]:
            raise OSError("unavailable")
        return self.fake(method, params)

    def test_natural_language_intents_and_citations(self):
        questions = {
            "What is my wallet balance?": "balances",
            "How many shares are in my positions?": "positions",
            "Which vaults hold assets?": "vaults",
            "Where is my USDC?": "exposure",
            "Compare RockawayX versus SharpByte": "compare",
            "What's my biggest position?": "largest",
            "What am I earning in yield?": "earnings",
        }
        for question, intent in questions.items():
            with self.subTest(intent=intent):
                result = answer(WALLET, question, self.fake)
                self.assertEqual(result["intent"], intent)
                self.assertEqual(result["question"], question)
                self.assertEqual(result["block"], int(BLOCK, 16))
                if intent == "positions":
                    self.assertTrue(all(vault["shares"]["value"] == "5" and
                                        vault["underlying_usdc_raw"]["value"] in {"9", "12"}
                                        for vault in result["vaults"].values()))
                if intent == "vaults":
                    self.assertEqual({v["asset"] for v in result["vaults"].values()}, {USDC})
                if intent == "exposure":
                    self.assertEqual(result["total_usdc_raw"]["value"], "24")
                    self.assertEqual(result["total_usdc_raw"]["contract"], USDC)
                if intent in ("compare", "largest", "earnings"):
                    field = {"compare": "comparison", "largest": "largest_position", "earnings": "earnings"}[intent]
                    for name, source in result[field]["sources"].items():
                        self.assertEqual(source["contract"], USDC if name == "Wallet USDC" else VAULTS[name])
                        self.assertEqual(source["block"], int(BLOCK, 16))
                if intent == "compare":
                    self.assertEqual(result["comparison"]["value"], "SharpByte > RockawayX")
                if intent == "largest":
                    self.assertEqual(result["largest_position"]["value"], "SharpByte")
                if intent == "earnings":
                    self.assertEqual(result["earnings"]["value"], "unknown")
        self.assertTrue(all(method in {"eth_chainId", "eth_blockNumber", "eth_getCode", "eth_call", "eth_getBalance"}
                            for method, _ in self.seen))

    def test_usdc_balance_questions_respect_wallet_and_vault_objects(self):
        wallet = answer(WALLET, "How much USDC is in my wallet?", self.fake)
        self.assertEqual(wallet["intent"], "balances")
        self.assertEqual(wallet["wallet_balances"]["USDC_raw"]["value"], "3")

        for question in ("What is my PROS balance?", "How much USDC and PROS do I have in my wallet?"):
            with self.subTest(question=question):
                self.assertEqual(answer(WALLET, question, self.fake)["wallet_balances"]["PROS_wei"]["value"], "7")

        rockaway = answer(WALLET, "How much USDC do I have in RockawayX?", self.fake)
        self.assertEqual(rockaway["intent"], "positions")
        self.assertEqual(set(rockaway["vaults"]), {"RockawayX"})
        self.assertEqual(rockaway["vaults"]["RockawayX"]["underlying_usdc_raw"],
                         {"value": "9", "contract": VAULTS["RockawayX"], "block": int(BLOCK, 16),
                          "method": "convertToAssets(uint256)"})

        across = answer(WALLET, "How much USDC across vaults?", self.fake)
        self.assertEqual(across["intent"], "vaults")
        self.assertEqual({name: v["underlying_usdc_raw"]["value"] for name, v in across["vaults"].items()},
                         {"RockawayX": "9", "SharpByte": "12"})
        self.assertNotIn("wallet_balances", across)

    def test_explicit_objects_preserved_across_intents(self):
        for question in ("How much USDC is in my wallet and RockawayX?",
                         "Where is my USDC in my wallet and RockawayX?",
                         "What is my largest position in my wallet and RockawayX?",
                         "What are my earnings in my wallet and RockawayX?"):
            with self.subTest(question=question):
                result = answer(WALLET, question, self.fake)
                if result["intent"] == "earnings":
                    self.assertEqual(set(result["earnings"]["sources"]), {"Wallet USDC", "RockawayX"})
                else:
                    self.assertEqual(set(result["vaults"]), {"RockawayX"})
                    self.assertEqual(set(result["wallet_balances"]), {"USDC_raw"})
                if result["intent"] == "exposure":
                    self.assertEqual(result["total_usdc_raw"]["value"], "12")
                if result["intent"] == "largest":
                    self.assertEqual(result["largest_position"]["value"], "RockawayX")
        result = answer(WALLET, "Where is my USDC in SharpByte?", self.broken)
        self.assertEqual(set(result["vaults"]), {"SharpByte"})
        self.assertNotIn("wallet_balances", result)
        self.assertEqual(result["total_usdc_raw"]["value"], "12")
        self.assertEqual(set(answer(WALLET, "USDC balance", self.fake)["wallet_balances"]), {"USDC_raw"})
        self.assertEqual(set(answer(WALLET, "PROS balance", self.fake)["wallet_balances"]), {"PROS_wei"})

    def test_comparison_uses_only_requested_objects(self):
        for question, names, expected in (
                ("Compare wallet USDC and RockawayX", {"Wallet USDC", "RockawayX"}, "RockawayX > Wallet USDC"),
                ("Compare RockawayX versus my wallet", {"Wallet USDC", "RockawayX"}, "RockawayX > Wallet USDC"),
                ("Compare wallet and SharpByte", {"Wallet USDC", "SharpByte"}, "SharpByte > Wallet USDC"),
                ("Compare RockawayX", {"RockawayX"}, "unknown")):
            with self.subTest(question=question):
                result = answer(WALLET, question, self.fake)
                self.assertEqual(set(result["comparison"]["sources"]), names)
                self.assertEqual(result["comparison"]["value"], expected)
                self.assertEqual(set(result.get("vaults", {})), names - {"Wallet USDC"})
        result = answer(WALLET, "Compare wallet and SharpByte", self.broken)
        self.assertEqual(result["comparison"]["value"], "SharpByte > Wallet USDC")
        result = answer(WALLET, "Compare wallet and RockawayX", self.broken)
        self.assertEqual(result["comparison"]["value"], "unknown")
        self.assertEqual(result["comparison"]["sources"]["RockawayX"]["value"], "unknown")

    def test_three_position_comparison_preserves_ties_and_unknowns(self):
        cases = (
            ((9, 9, 12), "SharpByte > Wallet USDC = RockawayX"),
            ((9, 12, 9), "RockawayX > Wallet USDC = SharpByte"),
            ((12, 9, 9), "Wallet USDC > RockawayX = SharpByte"),
            ((12, 12, 9), "Wallet USDC = RockawayX > SharpByte"),
            ((12, 9, 12), "Wallet USDC = SharpByte > RockawayX"),
            ((9, 12, 12), "RockawayX = SharpByte > Wallet USDC"),
            ((3, 9, 12), "SharpByte > RockawayX > Wallet USDC"),
            ((3, 12, 9), "RockawayX > SharpByte > Wallet USDC"),
            ((9, 3, 12), "SharpByte > Wallet USDC > RockawayX"),
            ((9, 12, 3), "RockawayX > Wallet USDC > SharpByte"),
            ((12, 3, 9), "Wallet USDC > SharpByte > RockawayX"),
            ((12, 9, 3), "Wallet USDC > RockawayX > SharpByte"),
            ((9, 9, 9), "equal"),
            ((None, 9, 9), "unknown"),
            ((9, None, 9), "unknown"),
            ((9, 9, None), "unknown"),
        )
        for amounts, expected in cases:
            with self.subTest(amounts=amounts):
                amounts_by_contract = dict(zip((USDC, *VAULTS.values()), amounts))

                def values(method, params):
                    result = self.fake(method, params)
                    if method == "eth_call" and (params[0]["data"].startswith("0x07a2d13a") or
                            params[0]["to"] == USDC and params[0]["data"].startswith("0x70a08231")):
                        amount = amounts_by_contract[params[0]["to"]]
                        if amount is None:
                            raise OSError("unavailable")
                        return "0x" + format(amount, "064x")
                    return result

                comparison = answer(WALLET, "Compare wallet and RockawayX and SharpByte", values)["comparison"]
                self.assertEqual(comparison["value"], expected)
                self.assertEqual({name: item["value"] for name, item in comparison["sources"].items()},
                                 dict(zip(("Wallet USDC", *VAULTS),
                                          ("unknown" if amount is None else str(amount) for amount in amounts))))
                self.assertEqual(comparison["reason"], None if None not in amounts else
                                 "Need at least two available USDC positions")

    def test_harmless_wording_keeps_scope_guard(self):
        for question in ("Please show my wallet balance", "What is my current USDC balance?",
                         "Please show current USDC in my wallet and RockawayX"):
            with self.subTest(question=question):
                result = answer(WALLET, question, self.fake)
                self.assertEqual(result["wallet_balances"]["USDC_raw"]["value"], "3")
        self.seen.clear()
        for question in ("Please show my current BTC balance", "Please show USDC in Aave",
                         "Please show current USDC in my wallet and RockawayX and Aave",
                         "Please show my current PROS exposure", "Please show PROS in my wallet and RockawayX"):
            with self.subTest(question=question):
                with self.assertRaisesRegex(ValueError, "Unsupported scope"):
                    answer(WALLET, question, self.fake)
        self.assertEqual(self.seen, [])

    def test_unsupported_or_mixed_scopes_rejected_before_rpc(self):
        questions = (
            "How much USDC do I have in Aave?",
            "Where is my BTC?",
            "What is my PROS exposure?",
            "How much USDC do I have in RockawayX and Aave?",
            "Compare SharpByte versus Uniswap",
            "Where is my USDC and BTC?",
            "What is my PROS and USDC exposure?",
            "How much PROS do I have in RockawayX?",
            "How much DAI do I have?",
            "How much USDC do I have in MysteryVault?",
            "Where is my WBTC?",
            "What are my PROS earnings?",
        )
        for question in questions:
            with self.subTest(question=question):
                with self.assertRaisesRegex(ValueError, "Unsupported scope"):
                    answer(WALLET, question, self.fake)
        self.assertEqual(self.seen, [])

    def test_earnings_need_historical_evidence(self):
        result = answer(WALLET, "What am I earning?", self.fake)
        self.assertEqual(result["intent"], "earnings")
        for question in ("How much have I earned?", "What are my returns?"):
            self.assertEqual(answer(WALLET, question, self.fake)["intent"], "earnings")
        self.assertEqual(result["earnings"]["value"], "unknown")
        self.assertIn("historical", result["earnings"]["reason"].lower())
        self.assertEqual({name: v["block"] for name, v in result["earnings"]["sources"].items()},
                         {"RockawayX": int(BLOCK, 16), "SharpByte": int(BLOCK, 16)})

    def test_unknown_propagates_and_invalid_input_rejected(self):
        for question, field in (("Where is my USDC?", "total_usdc_raw"),
                                ("Compare vault values", "comparison"),
                                ("What is my largest position?", "largest_position")):
            with self.subTest(question=question):
                result = answer(WALLET, question, self.broken)
                self.assertEqual(result["vaults"]["RockawayX"]["underlying_usdc_raw"]["value"], "unknown")
                self.assertEqual(result[field]["value"], "unknown")
        with self.assertRaises(ValueError):
            answer("invalid", "balances", self.fake)
        with self.assertRaises(ValueError):
            answer(WALLET, "Tell me a joke", self.fake)
        with self.assertRaises(ValueError):
            answer(WALLET, None, self.fake)

    def test_equal_and_empty_vault_values(self):
        def same(method, params):
            value = self.fake(method, params)
            if method == "eth_call" and params[0]["data"].startswith("0x07a2d13a"):
                return "0x" + format(9, "064x")
            return value
        self.assertEqual(answer(WALLET, "Compare vaults", same)["comparison"]["value"], "equal")

        def empty(method, params):
            value = self.fake(method, params)
            if method == "eth_call" and (params[0]["data"].startswith("0x07a2d13a") or
                                         (params[0]["to"] == USDC and params[0]["data"].startswith("0x70a08231"))):
                return "0x" + "0" * 64
            return value
        self.assertEqual(answer(WALLET, "Biggest position?", empty)["largest_position"]["value"], "none")

    def test_wallet_balance_can_be_largest(self):
        def large_wallet(method, params):
            value = self.fake(method, params)
            if method == "eth_call" and params[0]["to"] == USDC and params[0]["data"].startswith("0x70a08231"):
                return "0x" + format(20, "064x")
            return value
        result = answer(WALLET, "What's my largest position?", large_wallet)["largest_position"]
        self.assertEqual(result["value"], "Wallet USDC")
        self.assertEqual(result["sources"]["Wallet USDC"]["contract"], USDC)


if __name__ == "__main__":
    unittest.main()

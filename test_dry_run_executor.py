import json
import unittest

import dry_run_executor as subject


class DryRunExecutorTests(unittest.TestCase):
    def test_success_reports_cost_and_expected_native_balances(self):
        calls = []

        def tool(name, arguments):
            calls.append((name, arguments))
            replies = {
                "get_chain_info": {"chainId": 1672, "chainIdMatches": True, "latestBlockHex": "0x10"},
                "get_gas_price": {"gasPrice": "0x5"},
                "estimate_gas": {"gas": "0x5208"},
                "eth_call": {"result": "0x"},
            }
            if name == "get_balance":
                return {"balance": hex(200000) if arguments["address"].endswith("01") else "0x7"}
            return replies[name]

        tx = {"from": "0x" + "0" * 39 + "1", "to": "0x" + "0" * 39 + "2", "value": "0xa"}
        report = subject.simulate(tx, tool)
        self.assertEqual("success", report["simulation"]["status"])
        self.assertEqual(21000, report["gas"]["estimate"])
        self.assertEqual("105000", report["gas"]["estimated_cost_wei"])
        self.assertEqual("94990", report["outcome"]["expected"]["from_balance_wei"])
        self.assertEqual("17", report["outcome"]["expected"]["to_balance_wei"])
        self.assertFalse(report["execution"]["broadcast_available"])
        self.assertFalse(report["execution"]["blocked"])
        self.assertEqual(["eth_call", "estimate_gas"], [name for name, _ in calls if name in ("eth_call", "estimate_gas")])

    def test_revert_blocks_execution_and_decodes_reason(self):
        revert = "0x08c379a0" + (32).to_bytes(32, "big").hex() + (4).to_bytes(32, "big").hex() + b"nope".hex().ljust(64, "0")

        def tool(name, arguments):
            if name == "get_chain_info":
                return {"chainId": 1672, "chainIdMatches": True, "latestBlockHex": "0x11"}
            if name == "get_gas_price":
                return {"gasPrice": "0x5"}
            if name == "get_balance":
                return {"balance": "0x0"}
            if name == "eth_call":
                raise subject.ToolError("execution reverted", {"data": revert})
            self.fail(f"unexpected call after failed simulation: {name}")

        report = subject.simulate({"to": "0x" + "0" * 40, "data": "0xdeadbeef"}, tool)
        self.assertEqual("revert", report["simulation"]["status"])
        self.assertEqual("nope", report["simulation"]["revert_reason"])
        self.assertTrue(report["execution"]["blocked"])
        self.assertEqual("simulation_failed", report["execution"]["reason"])
        self.assertIsNone(report["gas"]["estimate"])

    def test_estimation_revert_blocks_execution(self):
        def tool(name, arguments):
            replies = {
                "get_chain_info": {"chainId": 1672, "chainIdMatches": True, "latestBlockHex": "0x12"},
                "get_balance": {"balance": "0x0"},
                "eth_call": {"result": "0x"},
            }
            if name == "estimate_gas":
                raise subject.ToolError("execution reverted: denied")
            return replies[name]

        report = subject.simulate({"to": "0x" + "0" * 40}, tool)
        self.assertEqual("revert", report["simulation"]["status"])
        self.assertEqual("denied", report["simulation"]["revert_reason"])
        self.assertTrue(report["execution"]["blocked"])

    def test_revert_without_reason_reports_null(self):
        self.assertIsNone(subject.decode_revert(None, "execution reverted: "))

    def test_rejects_invalid_transaction_before_rpc(self):
        with self.assertRaisesRegex(ValueError, "to must be"):
            subject.simulate({"to": "wrong"}, lambda *_: self.fail("RPC called"))


if __name__ == "__main__":
    unittest.main()

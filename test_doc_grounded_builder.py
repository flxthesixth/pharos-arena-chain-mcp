import unittest

from doc_grounded_builder import Builder, RequestNotCovered


DOCS = {
    "chain_id": "Use eth_chainId; expect 0x688.\n# Sources\n- https://docs.pharos.xyz/api-and-sdk/json-rpc-methods\n- https://docs.pharos.xyz/getting-started/network/pacific-mainnet",
    "block_number": "Use eth_blockNumber; result is hexadecimal.\n# Sources\n- https://docs.pharos.xyz/api-and-sdk/json-rpc-methods",
    "balance": "Use eth_getBalance; result is wei.\n# Sources\n- https://docs.pharos.xyz/api-and-sdk/json-rpc-methods",
}


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.docs_calls = []
        self.chain_calls = []

        def docs(question):
            self.docs_calls.append(question)
            return DOCS[next(key for key in DOCS if key.replace("_", " ") in question.lower())]

        def chain(tool, arguments):
            self.chain_calls.append((tool, arguments))
            return {
                "get_chain_info": {"chainId": 1672, "chainIdHex": "0x688", "chainIdMatches": True,
                                   "latestBlock": "99", "latestBlockHex": "0x63"},
                "get_block_number": {"blockNumber": "99", "blockNumberHex": "0x63"},
                "get_balance": {"address": arguments.get("address"), "balanceWei": "0",
                                "balance": "0", "symbol": "PROS", "balanceHex": "0x0"},
            }[tool]

        self.builder = Builder(docs, chain)

    def test_chain_id_is_planned_executed_and_verified(self):
        output = self.builder.run("How do I check the Pharos chain ID?")
        self.assertEqual(output["status"], "success")
        self.assertEqual(output["execution"]["tool"], "get_chain_info")
        self.assertTrue(output["verification"]["matches_plan"])
        self.assertEqual(output["plan"]["sources"][1],
                         "https://docs.pharos.xyz/getting-started/network/pacific-mainnet")
        self.assertEqual(len(self.docs_calls), 1)

    def test_latest_block_is_checked_in_hex_and_decimal(self):
        output = self.builder.run("How do I get the latest block number?")
        self.assertEqual(output["execution"]["tool"], "get_block_number")
        self.assertTrue(output["verification"]["checks"]["hex_matches_decimal"])

    def test_zero_address_balance_is_read_only_and_verified(self):
        address = "0x0000000000000000000000000000000000000000"
        output = self.builder.run(f"How do I read native balance for {address}?")
        self.assertEqual(self.chain_calls[0], ("get_balance", {"address": address, "block": "latest"}))
        self.assertTrue(output["verification"]["checks"]["units_match"])
        self.assertFalse(output["execution"]["requires_signature"])

    def test_unknown_request_asks_docs_then_reports_no_coverage_without_chain_call(self):
        self.builder.docs_ask = lambda question: "No documentation for Anchor deployment.\n# Sources\n- https://docs.pharos.xyz/introduction/readme"
        output = self.builder.run("How do I deploy a Solana program with Anchor?")
        self.assertEqual(output["status"], "unsupported")
        self.assertIn("no coverage", output["message"].lower())
        self.assertEqual(self.chain_calls, [])

    def test_missing_docs_citations_blocks_chain_execution(self):
        self.builder.docs_ask = lambda question: "Use eth_chainId."
        with self.assertRaises(RequestNotCovered):
            self.builder.run("How do I check the Pharos chain ID?")
        self.assertEqual(self.chain_calls, [])


if __name__ == "__main__":
    unittest.main()

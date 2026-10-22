import unittest
from decimal import Decimal

import natural_language_payment_agent as subject

SENDER = "0x1478c81e94a7d7751b344f99fef7b90d1260dfef"
RECIPIENT = "0x00000000000000000000000000000000000000aa"


class Result:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def runner(command, **_):
    key = tuple(command[1:-2])
    replies = {
        ("block-number",): "31724121\n",
        ("chain-id",): "688689\n",
        ("balance", SENDER, "--block", "31724121"): "2000000000000000000\n",
        ("estimate", RECIPIENT, "--from", SENDER, "--value", "500000000000000000",
         "--block", "31724121"): "21000\n",
        ("gas-price",): "1000000000\n",
        ("code", subject.TOKENS["USDC"][0], "--block", "31724121"): "0x6000\n",
        ("call", subject.TOKENS["USDC"][0], "symbol()(string)", "--block", "31724121"): '"USDC"\n',
        ("call", subject.TOKENS["USDC"][0], "decimals()(uint8)", "--block", "31724121"): "6\n",
        ("call", subject.TOKENS["USDC"][0], "balanceOf(address)(uint256)", SENDER,
         "--block", "31724121"): "2500000\n",
        ("call", subject.TOKENS["USDC"][0], "transfer(address,uint256)(bool)", RECIPIENT,
         "1250000", "--from", SENDER, "--block", "31724121"): "true\n",
    }
    return Result(replies[key])


class PaymentAgentTests(unittest.TestCase):
    def test_erc20_request_validates_and_emits_unsigned_wallet_request(self):
        report = subject.prepare(f"Please send 1.25 USDC to {RECIPIENT}", SENDER, runner)
        self.assertEqual("ready_for_wallet", report["status"])
        self.assertIn("Send 1.25 USDC", report["summary"])
        self.assertEqual("2.5", report["validation"]["sender_balance"])
        self.assertTrue(report["validation"]["token_contract_code_and_metadata_valid"])
        self.assertTrue(report["validation"]["transfer_simulation_succeeded"])
        tx = report["unsigned_transaction"]
        self.assertEqual(subject.TOKENS["USDC"][0], tx["to"])
        self.assertEqual("0x0", tx["value"])
        self.assertEqual(subject.encode_transfer(RECIPIENT, 1_250_000), tx["data"])
        self.assertEqual([tx], report["wallet_request"]["params"])
        self.assertEqual({"signed": False, "broadcast": False, "private_key_requested": False,
                          "user_wallet_confirmation_required": True}, report["safety"])

    def test_native_request_emits_value_transfer(self):
        report = subject.prepare(f"Pay {RECIPIENT} 0.5 PHRS", SENDER, runner)
        self.assertEqual(RECIPIENT, report["unsigned_transaction"]["to"])
        self.assertEqual(hex(500_000_000_000_000_000), report["unsigned_transaction"]["value"])
        self.assertNotIn("data", report["unsigned_transaction"])
        self.assertEqual(21000, report["validation"]["estimated_gas"])
        self.assertEqual(25200, report["validation"]["gas_limit"])
        self.assertEqual("0.0000252", report["validation"]["maximum_fee_phrs"])
        self.assertEqual("0.5000252", report["validation"]["required_total_phrs"])
        self.assertEqual(hex(25200), report["unsigned_transaction"]["gas"])
        self.assertEqual(hex(1_000_000_000), report["unsigned_transaction"]["gasPrice"])

    def test_missing_and_ambiguous_fields_request_follow_up_without_rpc(self):
        report = subject.prepare("Send some tokens to Alice", SENDER,
                                 lambda *_args, **_kwargs: self.fail("chain call made"))
        self.assertEqual("needs_clarification", report["status"])
        self.assertEqual(3, len(report["questions"]))
        self.assertIsNone(report["unsigned_transaction"])

    def test_multiple_tokens_are_ambiguous(self):
        report = subject.parse_request(f"Send 1 USDC or USDT to {RECIPIENT}")
        self.assertEqual("needs_clarification", report["status"])
        self.assertIn("Which single token", report["questions"][-1])

    def test_malformed_recipient_is_rejected_before_rpc(self):
        report = subject.prepare("Send 1 USDC to 0x1234", SENDER,
                                 lambda *_args, **_kwargs: self.fail("chain call made"))
        self.assertEqual("needs_clarification", report["status"])
        self.assertIn("malformed", report["questions"][0])

    def test_insufficient_balance_rejects_transaction(self):
        with self.assertRaisesRegex(subject.PaymentError, "Insufficient USDC balance"):
            subject.prepare(f"Send 3 USDC to {RECIPIENT}", SENDER, runner)

    def test_unknown_token_symbol_requires_contract(self):
        report = subject.parse_request(f"Send 1 DAI to {RECIPIENT}")
        self.assertEqual("needs_clarification", report["status"])
        self.assertIn("token contract address", report["questions"][-1])

    def test_amount_precision_is_exact(self):
        with self.assertRaisesRegex(subject.PaymentError, "more than 6 decimal"):
            subject.prepare(f"Send 0.0000001 USDC to {RECIPIENT}", SENDER, runner)
        self.assertEqual(1_250_000, subject.units(Decimal("1.25"), 6))

    def test_numeric_chain_response_accepts_cast_decimal_and_hex_formats(self):
        self.assertEqual(688689, subject.as_int("  688689\n"))
        self.assertEqual(688689, subject.as_int("\t0xA8231  "))

    def test_numeric_chain_response_accepts_cast_annotation_only_when_requested(self):
        output = "998999999988977630000000000 [9.989e26]"
        self.assertEqual(998999999988977630000000000,
                         subject.as_int(output, allow_cast_annotation=True))
        with self.assertRaisesRegex(subject.PaymentError, "Unexpected numeric chain response"):
            subject.as_int(output)

    def test_numeric_chain_response_rejects_trailing_garbage(self):
        for output in ("1 junk", "0x1 trailing", "688689 [6.886e5]", "1 [bad]", "0x1 [1e0]"):
            with self.subTest(output=output):
                with self.assertRaisesRegex(subject.PaymentError, "Unexpected numeric chain response"):
                    subject.as_int(output)

    def test_invalid_sender_is_rejected_before_rpc(self):
        with self.assertRaisesRegex(ValueError, "sender"):
            subject.prepare(f"Send 1 PHRS to {RECIPIENT}", "bad", runner)

    def test_negative_signed_and_zero_amounts_are_rejected_before_rpc(self):
        for amount in ("-1", "+1", "0"):
            with self.subTest(amount=amount):
                report = subject.prepare(f"Send {amount} USDC to {RECIPIENT}", SENDER,
                                         lambda *_args, **_kwargs: self.fail("chain call made"))
                self.assertEqual("needs_clarification", report["status"])
                self.assertIn("positive unsigned amount", report["questions"][0])

    def test_zero_recipient_is_rejected_before_rpc(self):
        report = subject.prepare("Send 1 USDC to 0x0000000000000000000000000000000000000000", SENDER,
                                 lambda *_args, **_kwargs: self.fail("chain call made"))
        self.assertEqual("needs_clarification", report["status"])
        self.assertIn("zero address", report["questions"][0])

    def test_native_balance_must_cover_value_plus_maximum_fee(self):
        def low_balance_runner(command, **kwargs):
            if tuple(command[1:-2]) == ("balance", SENDER, "--block", "31724121"):
                return Result("500020000000000000\n")
            return runner(command, **kwargs)

        with self.assertRaisesRegex(subject.PaymentError, "value plus maximum fee"):
            subject.prepare(f"Pay {RECIPIENT} 0.5 PHRS", SENDER, low_balance_runner)

    def test_erc20_transfer_simulation_revert_rejects_wallet_request(self):
        def reverting_runner(command, **kwargs):
            if tuple(command[1:4]) == ("call", subject.TOKENS["USDC"][0],
                                        "transfer(address,uint256)(bool)"):
                return Result(returncode=1, stderr="execution reverted: transfer blocked")
            return runner(command, **kwargs)

        with self.assertRaisesRegex(subject.PaymentError, "execution reverted: transfer blocked"):
            subject.prepare(f"Please send 1.25 USDC to {RECIPIENT}", SENDER, reverting_runner)


if __name__ == "__main__":
    unittest.main()

import io
import json
import socket
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

import batch_executor as subject


TARGET = "0x" + "11" * 20
BLOCK = "0x123"
BLOCK_HASH = "0x" + "ab" * 32
CODE = "0x60016000"


def encoded_results(items):
    bodies = []
    for success, data in items:
        blob = bytes.fromhex(data[2:])
        bodies.append(subject.word(success) + subject.word(64) + subject.word(len(blob)) + subject.padded(blob))
    cursor = 32 * len(bodies)
    array = subject.word(len(bodies)) + b"".join(
        subject.word(cursor + sum(map(len, bodies[:i]))) for i in range(len(bodies))
    ) + b"".join(bodies)
    return "0x" + (subject.word(32) + array).hex()


def actions(allow_failure=True):
    return [
        {"label": "one", "target": TARGET, "data": "0x11111111"},
        {"label": "two", "target": TARGET, "data": "0x22222222", "allow_failure": allow_failure},
        {"label": "three", "target": TARGET, "data": "0x33333333"},
    ]


class FakeRPC:
    def __init__(self, aggregate=None, aggregate_error=None, estimates=None):
        self.aggregate = aggregate or encoded_results([(True, "0x01"), (False, "0xdead"), (True, "0x03")])
        self.aggregate_error = aggregate_error
        self.estimates = iter(estimates or [90000, 40000, 45000, 50000])
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == "eth_chainId":
            return hex(subject.CHAIN_ID)
        if method == "eth_getBlockByNumber":
            return {"number": BLOCK, "hash": BLOCK_HASH, "timestamp": "0x65000000"}
        if method == "eth_getCode":
            return CODE
        if method == "eth_call" and params[0]["data"] == "0x" + subject.GET_CHAIN_ID_SELECTOR:
            return "0x" + subject.word(subject.CHAIN_ID).hex()
        if method == "eth_call":
            if self.aggregate_error:
                raise subject.RPCRemoteError(self.aggregate_error)
            return self.aggregate
        if method == "eth_estimateGas":
            return hex(next(self.estimates))
        self.fail(method)


class BatchExecutorTests(unittest.TestCase):
    def test_three_actions_use_one_pinned_block_and_compare_hypothetical_steps(self):
        rpc = FakeRPC()
        report = subject.execute(actions(), rpc, command="python3 batch_executor.py @batch-actions.json")

        self.assertEqual(subject.MULTICALL3, report["prepared_transaction"]["to"])
        self.assertEqual([1], report["partial_failure"]["failed_indexes"])
        self.assertTrue(report["partial_failure"]["continued"])
        self.assertEqual(2, report["comparison"]["hypothetical_separate_transactions"]["steps_saved"])
        self.assertEqual(45000, report["comparison"]["gas_estimate_observations"]["difference"])
        self.assertFalse(report["broadcast"])
        self.assertEqual(BLOCK, report["evidence"]["pinned_block"]["number"])
        self.assertEqual(BLOCK_HASH, report["evidence"]["pinned_block"]["hash"])
        self.assertEqual("https://rpc.pharos.xyz", report["evidence"]["rpc_endpoint"])
        self.assertEqual("python3 batch_executor.py @batch-actions.json", report["evidence"]["exact_command"])
        self.assertEqual(4, report["evidence"]["multicall3_code_size_bytes"])
        self.assertRegex(report["evidence"]["multicall3_code_sha256"], r"^0x[0-9a-f]{64}$")
        self.assertEqual(subject.CHAIN_ID, report["evidence"]["multicall3_get_chain_id"])

        methods = [method for method, _ in rpc.calls]
        self.assertLess(methods.index("eth_getCode"), methods.index("eth_estimateGas"))
        for method, params in rpc.calls:
            if method == "eth_getCode":
                self.assertEqual(BLOCK, params[1])
            if method in ("eth_call", "eth_estimateGas"):
                self.assertEqual(BLOCK, params[1])

    def test_strict_aggregate_revert_returns_structured_failure_and_nonzero(self):
        rpc = FakeRPC(aggregate_error="execution reverted: Multicall3: call failed")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = subject.main(
                ["@batch-actions.json"],
                rpc_call=rpc,
                input_loader=lambda _: json.dumps(actions(allow_failure=False)),
                command="python3 batch_executor.py @batch-actions.json",
            )

        failure = json.loads(stderr.getvalue())
        self.assertNotEqual(0, exit_code)
        self.assertEqual("failed", failure["status"])
        self.assertEqual("aggregate3_simulation_reverted", failure["error"]["code"])
        self.assertFalse(failure["prepared_success"])
        self.assertNotIn("prepared_transaction", failure)
        self.assertFalse(failure["broadcast"])
        self.assertEqual(BLOCK, failure["evidence"]["pinned_block"]["number"])
        self.assertFalse(any(method == "eth_estimateGas" for method, _ in rpc.calls))

    def test_impossible_strict_false_result_fails_closed(self):
        impossible = encoded_results([(True, "0x01"), (False, "0xdead"), (True, "0x03")])
        rpc = FakeRPC(aggregate=impossible)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            exit_code = subject.main(
                ["@batch-actions.json"],
                rpc_call=rpc,
                input_loader=lambda _: json.dumps(actions(allow_failure=False)),
            )

        failure = json.loads(stderr.getvalue())
        self.assertNotEqual(0, exit_code)
        self.assertEqual("failed", failure["status"])
        self.assertEqual("aggregate3_untrusted_result", failure["error"]["code"])
        self.assertIn("allow_failure=false", failure["error"]["message"])
        self.assertFalse(failure["prepared_success"])
        self.assertNotIn("prepared_transaction", failure)
        self.assertFalse(failure["broadcast"])
        self.assertEqual(BLOCK, failure["evidence"]["pinned_block"]["number"])
        self.assertFalse(any(method == "eth_estimateGas" for method, _ in rpc.calls))

    def test_rejects_empty_multicall_code_before_preparation(self):
        rpc = FakeRPC()
        original = rpc.__call__

        def empty_code(method, params):
            if method == "eth_getCode":
                rpc.calls.append((method, params))
                return "0x"
            return original(method, params)

        with self.assertRaisesRegex(RuntimeError, "no bytecode"):
            subject.execute(actions(), empty_code)
        self.assertFalse(any(method == "eth_estimateGas" for method, _ in rpc.calls))

    def test_rejects_multicall_get_chain_id_mismatch_before_preparation(self):
        rpc = FakeRPC()
        original = rpc.__call__

        def wrong_chain(method, params):
            if method == "eth_call" and params[0]["data"] == "0x" + subject.GET_CHAIN_ID_SELECTOR:
                rpc.calls.append((method, params))
                return "0x" + subject.word(1).hex()
            return original(method, params)

        with self.assertRaisesRegex(RuntimeError, "getChainId"):
            subject.execute(actions(), wrong_chain)
        self.assertFalse(any(method == "eth_estimateGas" for method, _ in rpc.calls))

    def test_decode_rejects_out_of_bounds_root_offset(self):
        raw = "0x" + subject.word(4096).hex() + subject.word(0).hex()
        with self.assertRaisesRegex(ValueError, "root offset"):
            subject.decode_aggregate3(raw, 1)

    def test_decode_rejects_out_of_bounds_item_offset(self):
        raw = "0x" + (subject.word(32) + subject.word(1) + subject.word(4096)).hex()
        with self.assertRaisesRegex(ValueError, "item offset"):
            subject.decode_aggregate3(raw, 1)

    def test_decode_rejects_out_of_bounds_blob_offset(self):
        body = subject.word(1) + subject.word(4096)
        raw = "0x" + (subject.word(32) + subject.word(1) + subject.word(32) + body).hex()
        with self.assertRaisesRegex(ValueError, "blob offset"):
            subject.decode_aggregate3(raw, 1)

    def test_rpc_wraps_timeout_malformed_json_and_missing_result(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return io.BytesIO(self.payload)

            def __exit__(self, *_):
                return False

        with patch.object(subject, "urlopen", side_effect=socket.timeout("timed out")):
            with self.assertRaisesRegex(subject.RPCError, "timed out"):
                subject.rpc("eth_chainId", [])
        with patch.object(subject, "urlopen", return_value=Response(b"not-json")):
            with self.assertRaisesRegex(subject.RPCError, "malformed JSON"):
                subject.rpc("eth_chainId", [])
        with patch.object(subject, "urlopen", return_value=Response(b'{"jsonrpc":"2.0","id":1}')):
            with self.assertRaisesRegex(subject.RPCError, "missing result"):
                subject.rpc("eth_chainId", [])

    def test_rejects_fewer_than_three_actions_before_rpc(self):
        with self.assertRaisesRegex(ValueError, "at least 3"):
            subject.execute([{"target": TARGET, "data": "0x"}], lambda *_: self.fail("RPC called"))


if __name__ == "__main__":
    unittest.main()

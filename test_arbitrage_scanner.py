import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from arbitrage_scanner import UINT256_MAX, SimulatedVenue, execute_prepared, scan, swap_calldata


NOW = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
BASE = {"symbol": "WPHRS", "address": "0x1111111111111111111111111111111111111111", "decimals": 18}
QUOTE = {"symbol": "USDC", "address": "0x2222222222222222222222222222222222222222", "decimals": 6}


def venue(source_id, base_reserve, quote_reserve, *, fail_query=False, fail_leg=None,
          base=BASE, quote=QUOTE, observed_at=NOW):
    return SimulatedVenue({
        "source_id": source_id,
        "mode": "simulated",
        "router": "0x" + ("a" if source_id.endswith("alpha") else "b") * 40,
        "base_asset": base,
        "quote_asset": quote,
        "base_reserve_atoms": str(base_reserve),
        "quote_reserve_atoms": str(quote_reserve),
        "fee_bps": 10,
        "gas_units": 120000,
        "observed_at": observed_at.isoformat(),
        "fail_query": fail_query,
        "fail_leg": fail_leg,
    })


class ArbitrageScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.log = Path(self.temp.name) / "scans.jsonl"
        self.config = {
            "base_asset": BASE,
            "quote_asset": QUOTE,
            "trade_size_quote_atoms": "1000000000",
            "minimum_net_profit_quote_atoms": "5000000",
            "max_quote_age_seconds": 60,
            "gas_price_quote_atoms_per_unit": "2",
            "execution_slippage_bps": 30,
            "recipient": "0x3333333333333333333333333333333333333333",
            "deadline_unix": 1792630800,
        }

    def adapters(self):
        # Alpha spot 100 USDC/WPHRS; beta spot 103 USDC/WPHRS.
        return [venue("simulated-alpha", 10_000 * 10**18, 1_000_000 * 10**6),
                venue("simulated-beta", 10_000 * 10**18, 1_030_000 * 10**6)]

    def test_queries_two_sources_and_prepares_executable_bundle(self):
        adapters = self.adapters()
        result = scan(adapters, self.config, self.log, now=NOW)
        self.assertEqual([a.query_count for a in adapters], [1, 1])
        self.assertEqual(result["decision"], "PREPARE")
        self.assertEqual(result["asset_pair"], "WPHRS/USDC")
        self.assertGreater(int(result["net_profit_quote_atoms"]), 5_000_000)
        self.assertEqual(len(result["source_reads"]), 2)
        for read in result["source_reads"]:
            self.assertEqual(read["request"]["pair"], "WPHRS/USDC")
            self.assertEqual(read["request"]["amount_in_quote_atoms"], "1000000000")
            self.assertIn("raw_response", read)
            self.assertIn("observed_at", read["raw_response"])
        bundle = result["prepared_execution"]
        self.assertEqual(bundle["type"], "unsigned-two-leg-simulated-calldata-bundle")
        self.assertEqual(len(bundle["calls"]), 2)
        self.assertTrue(all(call["calldata"].startswith("0x38ed1739") for call in bundle["calls"]))
        self.assertEqual(execute_prepared(bundle, adapters)["status"], "SIMULATED_SUCCESS")

    def test_below_threshold_has_no_bundle(self):
        adapters = [venue("simulated-alpha", 10_000 * 10**18, 1_000_000 * 10**6),
                    venue("simulated-beta", 10_000 * 10**18, 1_001_000 * 10**6)]
        result = scan(adapters, self.config, self.log, now=NOW)
        self.assertEqual(result["decision"], "SKIP")
        self.assertNotIn("prepared_execution", result)
        self.assertIn("does not exceed", result["reason"])

    def test_cost_identity_and_amount_aware_slippage(self):
        small = scan(self.adapters(), self.config, self.log, now=NOW)
        large_config = dict(self.config, trade_size_quote_atoms="2000000000")
        large = scan(self.adapters(), large_config, self.log, now=NOW)
        self.assertEqual(
            int(small["gross_spread_quote_atoms"]) - int(small["costs_quote_atoms"]["total"]),
            int(small["net_profit_quote_atoms"]),
        )
        self.assertGreater(
            int(large["costs_quote_atoms"]["price_impact_slippage"]),
            2 * int(small["costs_quote_atoms"]["price_impact_slippage"]),
        )
        self.assertEqual(
            int(small["net_profit_quote_atoms"]),
            int(small["route"]["actual_sell_output_quote_atoms"]) - 1_000_000_000
            - int(small["costs_quote_atoms"]["gas"]),
        )

    def test_rejects_bps_outside_closed_range(self):
        for key in ("execution_slippage_bps",):
            for invalid in (-1, 10001):
                with self.subTest(key=key, invalid=invalid):
                    result = scan(self.adapters(), dict(self.config, **{key: invalid}), self.log, now=NOW)
                    self.assertEqual(result["decision"], "ERROR")
                    self.assertIn("0..10000", result["reason"])
        bad = venue("simulated-alpha", 10**22, 10**12)
        bad.config["fee_bps"] = 10001
        result = scan([bad, self.adapters()[1]], self.config, self.log, now=NOW)
        self.assertEqual(result["decision"], "ERROR")
        self.assertIn("fee_bps must be in 0..10000", result["reason"])

    def test_top_level_validation_errors_are_logged(self):
        probes = (
            ("recipient", "bad", "invalid recipient"),
            ("deadline_unix", 2**256, "deadline_unix must be in 0..2^256-1"),
            ("trade_size_quote_atoms", 2**256, "trade_size_quote_atoms must be in 1..2^256-1"),
            ("minimum_net_profit_quote_atoms", -1, "minimum_net_profit_quote_atoms must be in 0..2^256-1"),
            ("max_quote_age_seconds", 2**256, "max_quote_age_seconds must be in 0..2^256-1"),
            ("gas_price_quote_atoms_per_unit", 2**256, "gas_price_quote_atoms_per_unit must be in 0..2^256-1"),
        )
        for key, invalid, message in probes:
            with self.subTest(key=key):
                result = scan(self.adapters(), dict(self.config, **{key: invalid}), self.log, now=NOW)
                self.assertEqual(result["decision"], "ERROR")
                self.assertIn(message, result["reason"])
        records = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual(len(records), len(probes))
        self.assertTrue(all(record["decision"] == "ERROR" for record in records))

    def test_invalid_config_timestamp_address_and_expired_deadline_are_logged(self):
        cases = (
            (None, NOW, "config must be an object"),
            (dict(self.config, base_asset=dict(BASE, address="bad")), NOW, "invalid base_asset.address"),
            (dict(self.config, deadline_unix=int(NOW.timestamp())), NOW, "after scan timestamp"),
            (self.config, NOW.replace(tzinfo=None), "timezone-aware"),
        )
        for config, now, message in cases:
            with self.subTest(message=message):
                result = scan(self.adapters(), config, self.log, now=now)
                self.assertEqual(result["decision"], "ERROR")
                self.assertIn(message, result["reason"])
        self.assertEqual(len(self.log.read_text().splitlines()), len(cases))

    def test_venue_uint_bounds_are_logged(self):
        fields = ("base_reserve_atoms", "quote_reserve_atoms", "gas_units")
        for field in fields:
            with self.subTest(field=field):
                bad = self.adapters()[0]
                bad.config[field] = str(UINT256_MAX + 1)
                result = scan([bad, self.adapters()[1]], self.config, self.log, now=NOW)
                self.assertEqual(result["decision"], "ERROR")
                self.assertIn(f"{field} must be in 1..2^256-1", result["reason"])

    def test_swap_calldata_checks_every_uint256_word(self):
        address = "0x1111111111111111111111111111111111111111"
        for field, args in (
            ("amount_in", (-1, 1, address, address, address, 1)),
            ("amount_out_min", (1, UINT256_MAX + 1, address, address, address, 1)),
            ("deadline", (1, 1, address, address, address, UINT256_MAX + 1)),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, f"{field} must be in 0\\.\\.2\\^256-1"):
                    swap_calldata(*args)

    def test_stale_quote_is_logged_as_error(self):
        stale = NOW - timedelta(seconds=61)
        result = scan([venue("simulated-alpha", 10**22, 10**12, observed_at=stale),
                       self.adapters()[1]], self.config, self.log, now=NOW)
        self.assertEqual(result["decision"], "ERROR")
        self.assertIn("stale", result["reason"])
        self.assertNotIn("prepared_execution", result)

    def test_asset_or_decimal_mismatch_is_logged_as_error(self):
        wrong = dict(BASE, decimals=8)
        result = scan([venue("simulated-alpha", 10**22, 10**12, base=wrong),
                       self.adapters()[1]], self.config, self.log, now=NOW)
        self.assertEqual(result["decision"], "ERROR")
        self.assertIn("asset metadata mismatch", result["reason"])

    def test_source_failure_queries_both_and_logs_error(self):
        adapters = [venue("simulated-alpha", 10**22, 10**12, fail_query=True), self.adapters()[1]]
        result = scan(adapters, self.config, self.log, now=NOW)
        self.assertEqual([a.query_count for a in adapters], [1, 1])
        self.assertEqual(result["decision"], "ERROR")
        self.assertIn("source query failed", result["reason"])

    def test_one_leg_failure_rolls_back_simulation(self):
        adapters = self.adapters()
        result = scan(adapters, self.config, self.log, now=NOW)
        adapters[1].config["fail_leg"] = "sell"
        execution = execute_prepared(result["prepared_execution"], adapters)
        self.assertEqual(execution["status"], "SIMULATED_REVERT")
        self.assertEqual(execution["completed_calls"], 0)
        self.assertIn("sell", execution["reason"])

    def test_every_attempt_appends_provenance_record(self):
        scan(self.adapters(), self.config, self.log, now=NOW)
        scan([venue("simulated-alpha", 10**22, 10**12, fail_query=True), self.adapters()[1]],
             self.config, self.log, now=NOW)
        records = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertEqual([record["decision"] for record in records], ["PREPARE", "ERROR"])
        self.assertTrue(all(record["scanner_mode"] == "DETERMINISTIC_SIMULATION_NOT_LIVE" for record in records))


if __name__ == "__main__":
    unittest.main()

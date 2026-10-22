"""Deterministic two-venue arbitrage scanner; simulation only, never live."""
import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

MODE = "DETERMINISTIC_SIMULATION_NOT_LIVE"
SELECTOR = "38ed1739"  # swapExactTokensForTokens(uint256,uint256,address[],address,uint256)
UINT256_MAX = 2**256 - 1


def integer(value, name, *, positive=False, maximum=UINT256_MAX):
    minimum = 1 if positive else 0
    message = f"{name} must be in {minimum}..2^256-1" if maximum == UINT256_MAX else f"{name} must be in {minimum}..{maximum}"
    if isinstance(value, bool):
        raise ValueError(message)
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(message) from error
    if (str(result) != str(value) and not isinstance(value, int)) or not minimum <= result <= maximum:
        raise ValueError(message)
    return result


def bps(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be in 0..10000")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be in 0..10000") from error
    if (str(result) != str(value) and not isinstance(value, int)) or not 0 <= result <= 10_000:
        raise ValueError(f"{name} must be in 0..10000")
    return result


def address(value, name):
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        raise ValueError(f"invalid {name}")
    try:
        int(value[2:], 16)
    except ValueError as error:
        raise ValueError(f"invalid {name}") from error
    return value.lower()


def asset(value, name):
    if not isinstance(value, dict) or not isinstance(value.get("symbol"), str):
        raise ValueError(f"invalid {name}")
    return {"symbol": value["symbol"], "address": address(value.get("address"), f"{name}.address"),
            "decimals": integer(value.get("decimals"), f"{name}.decimals", maximum=255)}


def word(value, name):
    return f"{integer(value, name):064x}"


def address_word(value):
    return "0" * 24 + address(value, "calldata address")[2:]


def swap_calldata(amount_in, amount_out_min, token_in, token_out, recipient, deadline):
    """ABI-encode UniswapV2-compatible swapExactTokensForTokens call."""
    return "0x" + SELECTOR + "".join((
        word(amount_in, "amount_in"), word(amount_out_min, "amount_out_min"), word(160, "path offset"),
        address_word(recipient), word(deadline, "deadline"), word(2, "path length"),
        address_word(token_in), address_word(token_out),
    ))


def cpmm_output(amount_in, reserve_in, reserve_out, fee_bps):
    amount_after_fee = amount_in * (10_000 - fee_bps)
    return amount_after_fee * reserve_out // (reserve_in * 10_000 + amount_after_fee)


class SimulatedVenue:
    """Independently configured constant-product venue queried through an adapter boundary."""

    def __init__(self, config):
        self.config = dict(config)
        self.query_count = 0

    @property
    def source_id(self):
        return self.config.get("source_id", "unknown")

    def query(self, base, quote, amount_in_quote_atoms, queried_at):
        self.query_count += 1
        request = {"pair": f"{base['symbol']}/{quote['symbol']}",
                   "amount_in_quote_atoms": str(amount_in_quote_atoms)}
        if self.config.get("fail_query"):
            raise RuntimeError(f"{self.source_id}: configured source query failure")
        own_base = asset(self.config.get("base_asset"), "venue base_asset")
        own_quote = asset(self.config.get("quote_asset"), "venue quote_asset")
        fee = bps(self.config.get("fee_bps"), "fee_bps")
        observed_at = self.config.get("observed_at")
        if observed_at == "NOW":
            observed_at = queried_at.isoformat()
        raw = {
            "source_id": self.source_id,
            "mode": self.config.get("mode"),
            "observed_at": observed_at,
            "pair": f"{own_base['symbol']}/{own_quote['symbol']}",
            "base_asset": own_base,
            "quote_asset": own_quote,
            "base_reserve_atoms": str(integer(self.config.get("base_reserve_atoms"), "base_reserve_atoms", positive=True)),
            "quote_reserve_atoms": str(integer(self.config.get("quote_reserve_atoms"), "quote_reserve_atoms", positive=True)),
            "fee_bps": fee,
            "router": address(self.config.get("router"), "router"),
            "gas_units": integer(self.config.get("gas_units"), "gas_units", positive=True),
        }
        if raw["mode"] != "simulated":
            raise ValueError(f"{self.source_id}: only simulated mode supported")
        return {"request": request, "raw_response": raw}

    def simulate_call(self, call):
        if self.config.get("fail_leg") == call["leg"]:
            raise RuntimeError(f"{self.source_id}: configured {call['leg']} leg failure")
        if call["to"].lower() != address(self.config.get("router"), "router"):
            raise RuntimeError(f"{self.source_id}: router mismatch")
        return {"source_id": self.source_id, "leg": call["leg"], "status": "SIMULATED_OK"}


def append_record(record, log_path):
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, separators=(",", ":")) + "\n")


def route_metrics(buy, sell, trade, gas_price):
    br, qr = int(buy["base_reserve_atoms"]), int(buy["quote_reserve_atoms"])
    sbr, sqr = int(sell["base_reserve_atoms"]), int(sell["quote_reserve_atoms"])
    ideal_base = trade * br // qr
    buy_after_fee_ideal = trade * (10_000 - buy["fee_bps"]) * br // (10_000 * qr)
    actual_base = cpmm_output(trade, qr, br, buy["fee_bps"])
    gross_output = ideal_base * sqr // sbr
    buy_fee = (ideal_base - buy_after_fee_ideal) * sqr // sbr
    sell_ideal = actual_base * sqr // sbr
    sell_after_fee_ideal = actual_base * (10_000 - sell["fee_bps"]) * sqr // (10_000 * sbr)
    actual_output = cpmm_output(actual_base, sbr, sqr, sell["fee_bps"])
    sell_fee = sell_ideal - sell_after_fee_ideal
    gas = (buy["gas_units"] + sell["gas_units"]) * gas_price
    gross = gross_output - trade
    # Residual after fee-only outputs is exact amount-aware CPMM price impact.
    price_impact = gross_output - actual_output - buy_fee - sell_fee
    costs = {"buy_venue_fee": buy_fee, "sell_venue_fee": sell_fee,
             "price_impact_slippage": price_impact, "gas": gas}
    costs["total"] = sum(costs.values())
    return {"buy": buy, "sell": sell, "base_out": actual_base, "actual_output": actual_output,
            "gross": gross, "costs": costs, "net": gross - costs["total"]}


def scan(venues, config, log_path, *, now=None):
    """Query every venue once, validate provenance, evaluate routes, and log decision."""
    now = now or datetime.now(timezone.utc)
    record = {"scan_timestamp": now.isoformat() if isinstance(now, datetime) else str(now),
              "scanner_mode": MODE, "source_reads": []}
    try:
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("scan timestamp must be timezone-aware")
        if not isinstance(config, dict):
            raise ValueError("config must be an object")
        base = asset(config.get("base_asset"), "base_asset")
        quote = asset(config.get("quote_asset"), "quote_asset")
        trade = integer(config.get("trade_size_quote_atoms"), "trade_size_quote_atoms", positive=True)
        threshold = integer(config.get("minimum_net_profit_quote_atoms"), "minimum_net_profit_quote_atoms")
        max_age = integer(config.get("max_quote_age_seconds"), "max_quote_age_seconds")
        gas_price = integer(config.get("gas_price_quote_atoms_per_unit"), "gas_price_quote_atoms_per_unit")
        tolerance = bps(config.get("execution_slippage_bps"), "execution_slippage_bps")
        recipient = address(config.get("recipient"), "recipient")
        deadline = integer(config.get("deadline_unix"), "deadline_unix")
        if deadline <= int(now.timestamp()):
            raise ValueError("deadline_unix must be after scan timestamp")
        record.update({"asset_pair": f"{base['symbol']}/{quote['symbol']}",
                       "units": {"base": base, "quote": quote, "all_amounts": "integer smallest-unit atoms"},
                       "trade_size_quote_atoms": str(trade)})
        failures = []
        for venue in venues:
            try:
                record["source_reads"].append(venue.query(base, quote, trade, now))
            except Exception as error:  # adapter failures become auditable scan decisions
                failures.append(str(error))
                record["source_reads"].append({"source_id": venue.source_id, "error": str(error)})
        if len(venues) < 2 or len({venue.source_id for venue in venues}) != len(venues):
            raise ValueError("at least 2 distinct configured sources required")
        if failures:
            raise ValueError("source query failed: " + "; ".join(failures))
        responses = [read["raw_response"] for read in record["source_reads"]]
        for response in responses:
            if response["base_asset"] != base or response["quote_asset"] != quote:
                raise ValueError(f"{response['source_id']}: asset metadata mismatch")
            try:
                stamp = datetime.fromisoformat(response["observed_at"])
            except (TypeError, ValueError) as error:
                raise ValueError(f"{response['source_id']}: invalid observed_at") from error
            if stamp.tzinfo is None or (now - stamp).total_seconds() > max_age or stamp > now:
                raise ValueError(f"{response['source_id']}: stale or future quote")
        routes = [route_metrics(buy, sell, trade, gas_price)
                  for buy in responses for sell in responses if buy["source_id"] != sell["source_id"]]
        best = max(routes, key=lambda item: item["net"])
        costs = {name: str(value) for name, value in best["costs"].items()}
        record.update({
            "route": {"buy_at": best["buy"]["source_id"], "sell_at": best["sell"]["source_id"],
                      "actual_buy_output_base_atoms": str(best["base_out"]),
                      "actual_sell_output_quote_atoms": str(best["actual_output"])},
            "gross_spread_quote_atoms": str(best["gross"]), "costs_quote_atoms": costs,
            "net_profit_quote_atoms": str(best["net"]),
            "minimum_net_profit_quote_atoms": str(threshold),
        })
        if best["net"] > threshold:
            minimum_base = best["base_out"] * (10_000 - tolerance) // 10_000
            minimum_quote = best["actual_output"] * (10_000 - tolerance) // 10_000
            calls = [
                {"leg": "buy", "source_id": best["buy"]["source_id"], "to": best["buy"]["router"],
                 "value": "0", "gas_limit": str(best["buy"]["gas_units"]),
                 "calldata": swap_calldata(trade, minimum_base, quote["address"], base["address"], recipient, deadline)},
                {"leg": "sell", "source_id": best["sell"]["source_id"], "to": best["sell"]["router"],
                 "value": "0", "gas_limit": str(best["sell"]["gas_units"]),
                 "calldata": swap_calldata(best["base_out"], minimum_quote, base["address"], quote["address"], recipient, deadline)},
            ]
            record["decision"] = "PREPARE"
            record["reason"] = f"net profit {best['net']} exceeds threshold {threshold} quote atoms"
            record["prepared_execution"] = {"type": "unsigned-two-leg-simulated-calldata-bundle",
                                              "atomic": True, "signed": False, "broadcast": False,
                                              "chain": "simulation-only", "calls": calls}
        else:
            record["decision"] = "SKIP"
            record["reason"] = f"net profit {best['net']} does not exceed threshold {threshold} quote atoms"
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        record["decision"] = "ERROR"
        record["reason"] = str(error)
    append_record(record, log_path)
    return record


def execute_prepared(bundle, venues):
    """Atomically simulate prepared calls; any leg failure rolls all legs back."""
    by_id = {venue.source_id: venue for venue in venues}
    try:
        results = [by_id[call["source_id"]].simulate_call(call) for call in bundle["calls"]]
    except (KeyError, RuntimeError, ValueError) as error:
        return {"status": "SIMULATED_REVERT", "completed_calls": 0, "atomic_rollback": True,
                "reason": str(error)}
    return {"status": "SIMULATED_SUCCESS", "completed_calls": len(results), "results": results,
            "broadcast": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="arbitrage_scanner_config.json")
    parser.add_argument("--log", default="evidence/arbitrage-scanner/scans.jsonl")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    venues = [SimulatedVenue(item) for item in config.pop("venues")]
    result = scan(venues, config, args.log)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

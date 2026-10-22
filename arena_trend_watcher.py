"""Persist and evaluate Pharos gas-price trends from Chain MCP; read-only."""
import argparse
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

MCP = "https://mcp.pharos.xyz/mcp"


def post(method, params, session=None):
    headers = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    if session:
        headers["Mcp-Session-Id"] = session
    request = Request(MCP, json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                      "params": params}).encode(), headers, method="POST")
    with urlopen(request, timeout=25) as response:
        body = response.read().decode()
        session = response.headers.get("Mcp-Session-Id") or session
    if body.startswith("event:"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    reply = json.loads(body)
    if "error" in reply:
        raise RuntimeError(reply["error"])
    return reply["result"], session


def tool(name, arguments, session):
    result, _ = post("tools/call", {"name": name, "arguments": arguments}, session)
    if result.get("isError"):
        raise RuntimeError(result["content"])
    return json.loads(next(item["text"] for item in result["content"] if item["type"] == "text"))


def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS observations (
        block INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, gas_price_wei INTEGER NOT NULL CHECK(gas_price_wei >= 0),
        source TEXT NOT NULL, triggered INTEGER NOT NULL CHECK(triggered IN (0, 1)))""")
    return db


def is_trend(values, min_step_bps):
    return all(current > previous and current * 10000 >= previous * (10000 + min_step_bps)
               for previous, current in zip(values, values[1:]))


def record(db, block, gas_price_wei, observed_at, observations, min_step_bps, source="Chain MCP"):
    if block < 0 or gas_price_wei < 0:
        raise ValueError("block and gas price must be non-negative")
    db.execute("BEGIN IMMEDIATE")
    existing = db.execute("SELECT triggered FROM observations WHERE block = ?", (block,)).fetchone()
    if existing is not None:
        db.rollback()
        return False, bool(existing[0])
    recent = [row[0] for row in db.execute(
        "SELECT gas_price_wei FROM observations ORDER BY block DESC LIMIT ?", (observations - 1,))]
    values = list(reversed(recent)) + [gas_price_wei]
    triggered = len(values) == observations and is_trend(values, min_step_bps)
    db.execute("INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
               (block, observed_at, gas_price_wei, source, int(triggered)))
    db.commit()
    return True, triggered


def history(db):
    return [{"block": row[0], "observed_at": row[1], "gas_price_wei": row[2],
             "gas_price_gwei": format(row[2] / 1_000_000_000, ".9f").rstrip("0").rstrip("."),
             "source": row[3], "trend_met": bool(row[4])}
            for row in db.execute("SELECT * FROM observations ORDER BY block")]


def observe_live(session):
    chain = tool("get_chain_info", {}, session)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    gas = tool("get_gas_price", {}, session)
    return int(chain["latestBlock"]), int(gas["gasPriceWei"]), datetime.now(timezone.utc).isoformat()


def self_test():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "state.sqlite3"
        db = connect(path)
        stamp = "2026-01-01T00:00:00+00:00"
        outcomes = []
        for block, value in [(1, 10), (2, 30), (3, 11), (4, 12), (5, 13)]:
            outcomes.append(record(db, block, value, stamp, 3, 0, "self-test"))
        assert outcomes[2] == (True, False)  # one spike in [10, 30, 11]
        assert outcomes[4] == (True, True)   # [11, 12, 13] meets trend at block 5
        db.close()
        restarted = connect(path)
        assert record(restarted, 5, 13, stamp, 3, 0, "self-test") == (False, True)
        rows = history(restarted)
        assert len(rows) == 5 and sum(row["block"] == 5 for row in rows) == 1
        restarted.close()
        return {"single_spike_triggered": rows[2]["trend_met"],
                "trigger_moment": next(row for row in rows if row["trend_met"]),
                "history_after_restart": rows, "duplicate_inserted": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, default=Path("trend-watcher-state.sqlite3"))
    parser.add_argument("--observations", type=int, default=3,
                        help="Consecutive observations required (minimum: 3)")
    parser.add_argument("--min-step-bps", type=int, default=0,
                        help="Minimum increase per step in basis points")
    parser.add_argument("--history", action="store_true", help="Print stored history without MCP access")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.observations < 3:
        parser.error("observations must be at least 3")
    if args.min_step_bps < 0:
        parser.error("min-step-bps must be non-negative")
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
        return
    db = connect(args.state)
    if args.history:
        print(json.dumps({"history": history(db)}, indent=2))
        return
    _, session = post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "arena-trend-watcher", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")
    block, value, stamp = observe_live(session)
    inserted, triggered = record(db, block, value, stamp, args.observations, args.min_step_bps)
    print(json.dumps({"observation": {"block": block, "gas_price_wei": value, "observed_at": stamp,
                                      "source": "Chain MCP"},
                      "stored": inserted, "duplicate_after_restart": not inserted,
                      "rule": {"observations": args.observations, "min_step_bps": args.min_step_bps},
                      "trend_met_now": triggered if inserted else False,
                      "history": history(db)}, indent=2))


if __name__ == "__main__":
    main()

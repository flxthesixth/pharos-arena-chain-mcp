# Trend Watcher — Pharos Agent Arena

Read-only gas-price trend watcher using hosted [Pharos Chain MCP](https://mcp.pharos.xyz/mcp). Each run reads current block and gas price, then atomically stores one observation per block in SQLite. Block primary key prevents duplicate history after restart. No wallet, key, transaction, or third-party package is used.

## Run

```bash
python3 arena_trend_watcher.py --self-test
python3 arena_trend_watcher.py
python3 arena_trend_watcher.py --history
```

Default state: `trend-watcher-state.sqlite3`. Rule defaults to three consecutive strictly increasing observations. Configure sample count and minimum per-step increase:

```bash
python3 arena_trend_watcher.py --observations 5 --min-step-bps 100
```

`--observations` cannot be below 3. `--min-step-bps 100` means each observation must rise at least 1%. Run once per new block; rerunning in same block reports `duplicate_after_restart: true` and does not insert or trigger again. Output includes full stored history and marks exact triggering observation with `trend_met: true`.

## Proof

`--self-test` persists `[10, 30, 11, 12, 13]`, closes and reopens database, and retries block 5. Single spike `[10, 30, 11]` does not trigger. Trend `[11, 12, 13]` triggers exactly at block 5. Restart retry leaves five rows, with one block-5 row.

Bounded live runs observed Pharos mainnet blocks `20882460` and `20882461`, each at gas price `10000000000` wei (`10` gwei), through Chain MCP. Second process reopened same SQLite file and retained first observation before adding second. Duplicate-block rejection is exercised by `--self-test`. Live values vary.

# Threshold Guardian — Pharos Agent Arena

Read-only Threshold Guardian evaluates three independent live chain conditions through hosted [Pharos Chain MCP](https://mcp.pharos.xyz/mcp): latest block via `get_chain_info`, gas price via `get_gas_price`, and USDC total supply via `eth_call`. It fires only when every condition passes. No wallet, key, transaction, or third-party Python package is used.

USDC contract: [`0xc879c018db60520f4355c26ed1a6d572cdac1815`](https://www.pharosscan.xyz/address/0xc879c018db60520f4355c26ed1a6d572cdac1815), Pharos mainnet chain ID 1672. Supply uses six USDC decimals. Contract read is pinned to reported block.

## Run

Python 3.9+ and outbound HTTPS required.

```bash
python3 threshold_guardian_self_test.py
python3 threshold_guardian.py --profile fire-demo
python3 threshold_guardian.py --profile hold-demo
```

Use another config with `--config path.json`. Each profile must contain at least three conditions. Supported metrics: `block_number`, `gas_price_gwei`, `usdc_total_supply`. Supported operators: `>`, `>=`, `<`, `<=`, `==`. Thresholds are decimal strings to preserve exact values.

## Decision trace

Each run prints one record per condition with live value, configured operator and threshold, and `passed`. Final `decision` is `FIRE` only when all records pass; otherwise it is `HOLD`. Included profiles deliberately use different valid policy limits against same kinds of live reads: `fire-demo` permits current expected operating range, while `hold-demo` requires stricter future block, gas, and supply limits. Values and block change with chain state.

Example shape:

```json
{
  "network": "Pharos mainnet",
  "chain_id": 1672,
  "block": 20882395,
  "profile": "fire-demo",
  "conditions": [
    {"metric": "block_number", "value": "20882395", "operator": ">=", "threshold": "20000000", "passed": true},
    {"metric": "gas_price_gwei", "value": "10", "operator": "<=", "threshold": "20", "passed": true},
    {"metric": "usdc_total_supply", "value": "48198775.206", "operator": ">=", "threshold": "40000000", "passed": true}
  ],
  "decision": "FIRE"
}
```

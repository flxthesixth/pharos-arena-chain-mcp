# Dry-Run Executor — Pharos Agent Arena

Stdlib-only Python CLI simulates a transaction on Pharos mainnet through hosted [Pharos Chain MCP](https://mcp.pharos.xyz/mcp). It pins `eth_call` and balance reads to latest observed block, runs `estimate_gas`, reads current gas price, and reports estimated cost plus native-balance outcome where available.

No private key, signing, or broadcast code exists. Failed `eth_call` returns `execution.blocked: true`, prints decoded Solidity `Error(string)` or `Panic(uint256)` data when available, and exits with status 2.

## Run

```bash
python3 -m unittest -v test_dry_run_executor.py
python3 dry_run_executor.py '{"to":"0xc879c018db60520f4355c26ed1a6d572cdac1815","data":"0x313ce567"}'
python3 dry_run_executor.py @transaction.json
```

Transaction JSON accepts MCP `eth_call` fields: `from`, `to`, `data`, `value`, `gas`, `gasPrice`, `maxFeePerGas`, `maxPriorityFeePerGas`, and `nonce`. `to` is required. Addresses, calldata, and quantities are validated before RPC use.

Output fields:

- `simulation.status`: `success` or `revert`
- `simulation.revert_reason`: decoded reason, raw revert data, or `null` when unavailable
- `gas`: estimate, gas price, and estimated maximum cost in wei
- `outcome.before`: pinned native balances
- `outcome.expected`: return data and expected native balances where derivable
- `execution`: explicit no-broadcast and automatic-block decision

Requires Python 3.9+ and outbound HTTPS. Network identity must match Pharos mainnet chain ID 1672.

# Read Contract State — Pharos Agent Arena

This small read-only script queries the hosted [Pharos Chain MCP](https://mcp.pharos.xyz/mcp) for four live values from the mainnet USDC contract, pins every contract call to the same block, and formats the supply with the token's reported decimals. It neither needs a wallet nor submits transactions.

Contract: [`0xc879c018db60520f4355c26ed1a6d572cdac1815`](https://www.pharosscan.xyz/address/0xc879c018db60520f4355c26ed1a6d572cdac1815) (Pharos mainnet, chain ID 1672).

Live proof: https://pharos-contract-state.pages.dev/

## Run

```bash
python3 arena_contract_state.py --self-test
python3 arena_contract_state.py
```

Requires Python 3.9+ and outbound HTTPS; no third-party Python packages. `arena_contract_state.py` uses the hosted MCP `get_chain_info` and `eth_call` tools. The four read-only selectors are `name()`, `symbol()`, `decimals()`, and `totalSupply()`.

## Sample output

Observed from the MCP server at block **20223132**. Values change with chain state:

```json
{
  "network": "Pharos mainnet",
  "chain_id": 1672,
  "contract": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
  "block": 20223132,
  "name": "USDC",
  "symbol": "USDC",
  "decimals": 6,
  "total_supply_raw": "23534395454922",
  "total_supply": "23534395.454922"
}
```

`total_supply` is expressed in USDC, not raw base units. No address fields occur in these four returned values; the contract address is labeled explicitly.

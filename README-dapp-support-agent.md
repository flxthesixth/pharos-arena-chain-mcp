# dApp Support Agent

Read-only CLI diagnoses failed Pharos mainnet transactions. It validates a transaction hash, fetches transaction and receipt through live Chain MCP, replays the call at the preceding block through Chain MCP `eth_call`, classifies the failure, and gives a plain explanation and fix. It never signs or sends transactions.

## Run

```bash
python3 dapp_support_agent.py --self-test
python3 dapp_support_agent.py 0x62f898330963ea18b1d48c41354ebcd4e9944c03f5bdc021cbd5969df0da2d72
python3 dapp_support_agent.py <0x-prefixed-64-hex-hash> --output evidence/dapp-support-agent/result.json
```

Python 3.9+ and outbound HTTPS required.

## Genuine failed-transaction evidence

Generated files under `evidence/dapp-support-agent/` contain raw transaction, receipt, historical replay, diagnosis, timestamp, and explorer URL from live Chain MCP.

| Failure type | Transaction |
|---|---|
| Slippage limit exceeded (`SLIPPAGE`) | [`0x62f898330963ea18b1d48c41354ebcd4e9944c03f5bdc021cbd5969df0da2d72`](https://www.pharosscan.xyz/tx/0x62f898330963ea18b1d48c41354ebcd4e9944c03f5bdc021cbd5969df0da2d72) |
| Insufficient native balance | [`0xbdf364aae1cd40ea554119ec7c6b63559026322eb6c69c28d4c0eaa413c4b0e3`](https://www.pharosscan.xyz/tx/0xbdf364aae1cd40ea554119ec7c6b63559026322eb6c69c28d4c0eaa413c4b0e3) |
| Application revert (`succeeded to fail`) | [`0x28d5a774d26ba1788995b937c5d5986b253abb5b2b982a2ea21f00d524db7d65`](https://www.pharosscan.xyz/tx/0x28d5a774d26ba1788995b937c5d5986b253abb5b2b982a2ea21f00d524db7d65) |

Each receipt has `status: 0x0`. Classification uses receipt gas plus historical `eth_call` evidence; no hashes, receipts, or diagnoses are fabricated.

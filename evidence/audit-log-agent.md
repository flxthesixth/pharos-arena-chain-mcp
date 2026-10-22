# Pharos Wallet Audit Log

- Wallet: `0x422615e302eb064a440f5be03400e03b6655abb6`
- Date range: `2026-10-22T00:57:00Z` through `2026-10-22T00:57:20Z`
- Blocks: `20882635`–`20882656`
- Source: Pharos Chain MCP (read-only)

## Totals

| Category | Count | Raw amounts by asset |
|---|---:|---|
| Transfers in | 2 | `0x52c48d4213107b20bc583832b0d951fb9ca8f0b0`: 207678634274357057418, `0xc879c018db60520f4355c26ed1a6d572cdac1815`: 123699829 |
| Transfers out | 1 | `0xc879c018db60520f4355c26ed1a6d572cdac1815`: 123699829 |
| Swaps | 0 | — |
| Approvals | 2 | `0x52c48d4213107b20bc583832b0d951fb9ca8f0b0`: 207678634274357057418, `0xc879c018db60520f4355c26ed1a6d572cdac1815`: 123699829 |
| Contract interactions | 0 | — |

## Notable transactions

| Time (UTC) | Category | Amount (raw) | Asset | Transaction |
|---|---|---:|---|---|
| 2026-10-22T00:57:08+00:00 | Transfers in | 207678634274357057418 | `0x52c48d4213107b20bc583832b0d951fb9ca8f0b0` | [0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc](https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc) |
| 2026-10-22T00:57:08+00:00 | Approvals | 207678634274357057418 | `0x52c48d4213107b20bc583832b0d951fb9ca8f0b0` | [0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc](https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc) |
| 2026-10-22T00:57:08+00:00 | Transfers in | 123699829 | `0xc879c018db60520f4355c26ed1a6d572cdac1815` | [0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc](https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc) |
| 2026-10-22T00:57:08+00:00 | Approvals | 123699829 | `0xc879c018db60520f4355c26ed1a6d572cdac1815` | [0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc](https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc) |
| 2026-10-22T00:57:08+00:00 | Transfers out | 123699829 | `0xc879c018db60520f4355c26ed1a6d572cdac1815` | [0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc](https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc) |

## Activity

```json
[
  {
    "category": "transfers_in",
    "tx_hash": "0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc",
    "block": 20882644,
    "transaction_index": 0,
    "log_index": 0,
    "timestamp": "2026-10-22T00:57:08+00:00",
    "asset": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
    "amount_raw": "123699829",
    "counterparty": "0xb143f6ca55358fac056eca7ac1a228a1f018b048",
    "method_selector": null,
    "explorer_url": "https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc"
  },
  {
    "category": "approvals",
    "tx_hash": "0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc",
    "block": 20882644,
    "transaction_index": 0,
    "log_index": 1,
    "timestamp": "2026-10-22T00:57:08+00:00",
    "asset": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
    "amount_raw": "123699829",
    "counterparty": "0x912c9ade24d44d8922f0866d8dcb079f1363f647",
    "method_selector": null,
    "explorer_url": "https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc"
  },
  {
    "category": "transfers_in",
    "tx_hash": "0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc",
    "block": 20882644,
    "transaction_index": 0,
    "log_index": 2,
    "timestamp": "2026-10-22T00:57:08+00:00",
    "asset": "0x52c48d4213107b20bc583832b0d951fb9ca8f0b0",
    "amount_raw": "207678634274357057418",
    "counterparty": "0x912c9ade24d44d8922f0866d8dcb079f1363f647",
    "method_selector": null,
    "explorer_url": "https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc"
  },
  {
    "category": "transfers_out",
    "tx_hash": "0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc",
    "block": 20882644,
    "transaction_index": 0,
    "log_index": 3,
    "timestamp": "2026-10-22T00:57:08+00:00",
    "asset": "0xc879c018db60520f4355c26ed1a6d572cdac1815",
    "amount_raw": "123699829",
    "counterparty": "0x912c9ade24d44d8922f0866d8dcb079f1363f647",
    "method_selector": null,
    "explorer_url": "https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc"
  },
  {
    "category": "approvals",
    "tx_hash": "0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc",
    "block": 20882644,
    "transaction_index": 0,
    "log_index": 5,
    "timestamp": "2026-10-22T00:57:08+00:00",
    "asset": "0x52c48d4213107b20bc583832b0d951fb9ca8f0b0",
    "amount_raw": "207678634274357057418",
    "counterparty": "0x52c48d4213107b20bc583832b0d951fb9ca8f0b0",
    "method_selector": null,
    "explorer_url": "https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc"
  }
]
```

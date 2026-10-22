# Audit-Log Agent

Read-only Pharos mainnet wallet activity collector. Accepts wallet plus ISO-8601 date range, reads genuine blocks and event logs from hosted Chain MCP, categorizes records deterministically, totals each category, and exports Markdown.

## Run

```bash
python3 audit_log_agent.py \
  0x422615e302eb064a440f5be03400e03b6655abb6 \
  2026-10-22T00:57:00Z 2026-10-22T00:57:20Z \
  --output audit-log-report.md \
  --json audit-log-report.json
```

Date-only values use UTC and include the full end date. Timestamp values require timezone offsets and use a half-open range: start included, end excluded. Default safety ceiling is 10,000 blocks; narrow the range or explicitly raise `--max-blocks` for larger audits.

Requirements: Python 3.9+, outbound HTTPS. Stdlib only. No key, signing, or transaction broadcast.

## Categories

- **Transfers in/out:** native PROS transactions and ERC-20 `Transfer` logs involving wallet.
- **Swaps:** wallet-sent contract calls whose first four calldata bytes match known router swap selectors.
- **Approvals:** ERC-20 `Approval` logs whose owner is wallet.
- **Contract interactions:** other wallet-sent transactions with calldata.

Category precedence for wallet-sent transactions is native transfer, known swap, then other contract interaction. ERC-20 logs remain separate activity records because one transaction can move several assets and change approvals. Totals preserve integer raw units per asset contract; this avoids unsafe assumptions about unknown token decimals.

## Output

Markdown contains:

- wallet, requested dates, resolved block range, network, and Chain MCP provenance;
- count and raw amount totals for every required category, including zero-count categories;
- ten largest records with Pharos explorer links;
- complete deterministic activity JSON.

Optional `--json` writes machine-readable evidence. Genuine example outputs:

- `evidence/audit-log-agent.md`
- `evidence/audit-log-agent.json`

Example covers blocks `20882635`–`20882656`, wallet `0x422615e302eb064a440f5be03400e03b6655abb6`, and transaction [`0x1fac…36cc`](https://www.pharosscan.xyz/tx/0x1fac66f3166c208df6da746de87d3084bd64c1fda8f2798e1a0fef965b1236cc).

## Verify

```bash
python3 -m unittest -v test_audit_log_agent.py
python3 -m py_compile audit_log_agent.py test_audit_log_agent.py
```

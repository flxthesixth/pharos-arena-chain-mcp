# Whale-Watching Agent — Pharos Agent Arena

Read-only, Python-standard-library agent. Tracks five or more configured addresses, queries real ERC-20 `Transfer` logs through hosted [Pharos Chain MCP](https://mcp.pharos.xyz/mcp), flags token-specific thresholds, labels known counterparties, links every move to PharosScan, and summarizes recent sent/received activity across all watched addresses. No wallet, private key, transaction signing, or broadcast path exists.

## Run

```bash
python3 -m unittest -v test_whale_watcher.py
python3 whale_watcher.py --config whale_watcher_config.json
python3 whale_watcher.py --config whale_watcher_config.json --output evidence/whale-watching-agent.json
```

Edit `watched_addresses`, `known_labels`, token metadata/`significant_threshold`, and `lookback_blocks` in `whale_watcher_config.json`. At least five valid EVM addresses are required. Log requests use indexed sender and recipient topics and page in Chain MCP's 1,000-block limit. Duplicate self-transfers are removed by transaction hash and log index.

Output contains:

- Chain MCP endpoint, read-only tools, chain identity, observation time, and scanned block range.
- Full configuration and per-address transfer count, significant count, sent total, received total, label, and explorer link.
- `recent_activity`: every matching move with amount, token, source/destination address and label, watched parties, threshold decision, plain-language explanation, and transaction explorer URL.
- `significant_moves`: threshold-matching subset.

`unknown` means no label was configured; agent never guesses identity. Values are token quantities, not fiat valuations. Evidence file is a live snapshot and existing public activity, not transactions created by this agent. No Arena submission or reviewer approval is implied.

# Event/Log Monitor — Pharos Agent Arena

A read-only Pharos USDC `Transfer` monitor using the hosted [Chain MCP](https://mcp.pharos.xyz/mcp). It filters by contract and `Transfer(address,address,uint256)` topic, polls new blocks, saves the next block in a local JSON state file, and decodes `from`, `to`, amount, transaction hash, and block. No wallet or private key is used.

Contract: [`0xc879c018db60520f4355c26ed1a6d572cdac1815`](https://www.pharosscan.xyz/address/0xc879c018db60520f4355c26ed1a6d572cdac1815), Pharos mainnet (chain ID 1672). Amount uses six USDC decimals.

## Run

```bash
python3 arena_event_monitor.py --self-test
python3 arena_event_monitor.py --backfill 100 --once
python3 arena_event_monitor.py --interval 15
```

Python standard library only. The first invocation scans recent blocks; later invocations resume after the last processed block via `event-monitor-state.json`. Use a single process per state file. For a larger history, use `--backfill N`; the monitor pages queries in windows of 1,000 blocks or fewer. `--once` runs one query cycle; without it the monitor keeps polling until interrupted.

## Live check

A bounded first run observed a USDC `Transfer` at block `20227240`, transaction [`0xe37a91fc46c840611549ba6596edcbe029459c407957a098c9e1b5b82431bbf9`](https://www.pharosscan.xyz/tx/0xe37a91fc46c840611549ba6596edcbe029459c407957a098c9e1b5b82431bbf9), amount `59.218683 USDC`. A second run using the saved state emitted no duplicate. In a separate continuous run with 12-second polling, the monitor later reported a `Transfer` at block `20227598`, transaction [`0x03fdbc3f5c591cc7b631ea3a68bd4c5de2e53d140841c925171904348d2c2818`](https://www.pharosscan.xyz/tx/0x03fdbc3f5c591cc7b631ea3a68bd4c5de2e53d140841c925171904348d2c2818), amount `184.664777 USDC`. These were existing public events, not transactions created for this test.

No task submission, points, or reviewer approval is implied by this README.

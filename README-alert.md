# On-Chain Alert Bot — Pharos Agent Arena

A read-only USDC `Transfer` monitor for Pharos mainnet that sends qualifying transactions to a Discord webhook. Chain data comes from [Pharos Chain MCP](https://mcp.pharos.xyz/mcp), chain ID 1672. It checks transfer amounts against a configurable minimum, includes addresses, value, block, and [explorer](https://www.pharosscan.xyz/) link, and stores a cursor after successful delivery.

## Run

Python 3.9+ and HTTPS access required. Create your own Discord webhook; keep its URL private. Do not put it in the repository or send it to the Arena.

```bash
python3 pharos_alert.py --self-test
export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN'
python3 pharos_alert.py --min-usdc 100 --interval 15
```

`--backfill 10` checks the ten most recent blocks on first run. `--once` processes one range and exits. Default local state file: `alert-state.json`; do not run two processes with the same state file. The monitor saves a cursor after each event and advances it only after webhook delivery returns successfully. If the process crashes after delivery but before cursor save, an event can be delivered twice. Discord does not offer an exactly-once webhook delivery guarantee.

## Verification

`python3 pharos_alert.py --self-test` checks threshold filtering, content, cursor deduplication, and failure handling. A live Chain MCP read over a 1,000-block range processed **83 existing public USDC transfers** through a mock sender; a second poll emitted **0 duplicates**. No Discord webhook was configured or sent to. This is **not** proof of a real-channel delivery and does not meet that Arena criterion yet.

No on-chain transaction, Arena submission, or reviewer approval is implied.

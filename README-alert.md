# On-Chain Alert Bot — Pharos Agent Arena

Read-only Pharos mainnet USDC `Transfer` monitor with verified Telegram `sendMessage` delivery and optional Discord webhook delivery. Chain data comes from [Pharos Chain MCP](https://mcp.pharos.xyz/mcp), chain ID 1672.

## Requirement coverage

- **Configurable condition:** `--min-usdc` controls minimum transfer value.
- **Real channel:** Telegram Bot API or Discord webhook, selected from environment variables.
- **Useful content:** every alert states transfer, value, sender, recipient, block, and [explorer transaction](https://www.pharosscan.xyz/) URL.
- **No repeat spam:** durable event ID is `tx_hash:log_index`. State records `pending` before network delivery and `delivered` with sanitized receipt after confirmed API success.

## Run monitor

Python 3.9+ and HTTPS access required. Keep credentials in environment only.

```bash
export TELEGRAM_BOT_TOKEN='YOUR_BOT_TOKEN'
export TELEGRAM_CHAT_ID='YOUR_CHAT_ID'
python3 pharos_alert.py --min-usdc 100 --interval 15
```

Discord remains supported:

```bash
export DISCORD_WEBHOOK_URL='https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN'
python3 pharos_alert.py --min-usdc 100 --once
```

Telegram takes precedence when both Telegram variables are set. `--backfill 10` checks ten latest blocks on first run. Default state is `alert-state.json`. Do not run two processes against one state file.

### Delivery semantics

Sender accepts delivery only after HTTP success and valid channel API response. Telegram receipt contains `platform`, masked `chat_id`, `message_id`, `delivered_at`, `http_success`, and `api_success`; it never contains bot token. Discord uses `wait=true` and validates returned message JSON.

State uses write-flush-`fsync`-atomic-replace. A `pending` record exists before channel access. Any sender exception becomes persistent `delivery_uncertain`; automatic retries remain blocked across restart because the channel may already have accepted the message. Operator must reconcile that event manually. Confirmed delivery becomes `delivered` with a sanitized receipt. This deliberately prefers no repeat spam over automatic retry after ambiguous outcomes.

## One-shot reviewer evidence

`generate_alert_evidence.py` accepts one genuine public decoded event JSON and sends exactly one clearly labeled `ARENA DEMO` alert using private environment variables. It rejects malformed transaction hashes/addresses, uses dedicated durable state, and refuses a repeated event.

Event shape:

```json
{
  "amount": "125.5",
  "from": "0x1111111111111111111111111111111111111111",
  "to": "0x2222222222222222222222222222222222222222",
  "block": 123,
  "tx_hash": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "log_index": 0,
  "symbol": "USDC"
}
```

Parent/operator invocation only:

```bash
export TELEGRAM_BOT_TOKEN='YOUR_BOT_TOKEN'
export TELEGRAM_CHAT_ID='YOUR_CHAT_ID'
python3 generate_alert_evidence.py genuine-public-event.json \
  --state alert-demo-state.json \
  --evidence evidence/on-chain-alert-delivery.json
```

Generated evidence contains event ID, public explorer URL, value, and sanitized delivery receipt. It contains no token, webhook URL, sender address, or recipient address.

## Verified real delivery

`evidence/on-chain-alert-delivery.json` records one real Telegram Bot API delivery of a clearly labelled `ARENA DEMO` alert:

- Genuine Pharos mainnet USDC `Transfer` at block `20882210`, log index `4`.
- Value: `1322.899203 USDC`.
- Telegram message ID: `8037`.
- Delivery time: `2026-10-22T02:30:06Z`.
- HTTP and Telegram API success: `true`.
- Returned chat ID and returned message text matched the request.
- Durable outbox status: `delivered`; a second invocation refused the same `tx_hash:log_index` before channel access.

The public event was independently checked against its successful mainnet transaction receipt. Telegram credential values and participant addresses are not present in the evidence file.

## Verification

```bash
python3 -m unittest -v test_pharos_alert.py test_generate_alert_evidence.py
python3 -m unittest discover -v
python3 -m compileall -q pharos_alert.py generate_alert_evidence.py test_pharos_alert.py test_generate_alert_evidence.py
```

Tests cover threshold/content, Telegram HTTP/API errors, successful sanitized receipt, delivered and uncertain-state duplicate suppression across restart, state persistence, one-shot labeling, sanitization, and malformed event rejection. Tests mock delivery; they send no message.

No on-chain transaction, real message, deployment, Arena submission, or reviewer approval is performed by tests or claimed here.

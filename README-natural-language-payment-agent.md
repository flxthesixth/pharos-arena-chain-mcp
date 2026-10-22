# Natural-Language Payment Agent — Pharos Agent Arena

Stdlib-only Python CLI converts free-text payment instructions into unsigned wallet requests. It uses public sender address only. It has no signing, private-key, or broadcast path.

## Acceptance coverage

1. Parses one positive unsigned amount, one token, and one nonzero `0x` recipient from free text. Missing, malformed, signed, nonpositive, or multiple values return `needs_clarification` with follow-up questions and no transaction.
2. Pins validation to one live Atlantic testnet block (`eip155:688689`). It validates recipient syntax; checks ERC-20 bytecode, live `symbol()` and `decimals()`, sender balance, and a sender-scoped `eth_call` transfer simulation. Native PHRS estimates gas, reserves a 1.2x gas limit at live gas price, and requires balance for value plus maximum fee. Insufficient balances and excessive decimal precision are rejected.
3. Prints human summary before `unsigned_transaction` in JSON output.
4. Returns unsigned EIP-1193 `eth_sendTransaction` wallet request only. User wallet must confirm, sign, and broadcast.

Supported symbols: `PHRS`, `USDC`, `USDT`, `WBTC`, `WETH`, `WPHRS`. Unknown ERC-20s work when request identifies address as `token 0x...` or `contract 0x...`; metadata and code are read live.

## Run

Requires Python 3.9+, Foundry `cast`, and outbound HTTPS.

```bash
python3 -m unittest -v test_natural_language_payment_agent.py

python3 natural_language_payment_agent.py \
  'Please send 1.25 USDC to 0x00000000000000000000000000000000000000aa' \
  --from 0x1478c81e94a7d7751b344f99fef7b90d1260dfef
```

Ambiguous example:

```bash
python3 natural_language_payment_agent.py \
  'Send some tokens to Alice' \
  --from 0x1478c81e94a7d7751b344f99fef7b90d1260dfef
```

## Genuine live evidence

`evidence/natural-language-payment-agent.json` records generated-at UTC time, exact command, RPC endpoint, fixed Atlantic block, source mode/version, and read-only validation:

- chain ID: `688689`
- USDC contract: `0xE0BE08c77f415F577A1B3A9aD7a1Df1479564ec8`
- live contract code, symbol `USDC`, decimals `6`, and successful sender-scoped transfer simulation
- sender live balance: `998999999988977630000` USDC
- requested amount: `1.25 USDC`
- output: ERC-20 `transfer(address,uint256)` calldata wrapped in unsigned `eth_sendTransaction`
- safety flags: `signed: false`, `broadcast: false`, wallet confirmation required

RPC: `https://atlantic.dplabs-internal.com`

Explorer: `https://atlantic.pharosscan.xyz`

No transaction was signed or submitted while producing evidence.

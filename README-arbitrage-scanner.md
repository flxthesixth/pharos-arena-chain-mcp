# Arbitrage Scanner

Deterministic simulation, **not live venues or market data**. Every scan invokes two independently configured constant-product venue adapters. Each adapter returns request provenance plus raw response: source ID, pair, requested amount, reserves, fee, router, gas units, and timestamp.

## Run

Python 3.9+; standard library only.

```bash
rm -f evidence/arbitrage-scanner/scans.jsonl
python3 arbitrage_scanner.py | tee evidence/arbitrage-scanner/profitable.json
python3 -m unittest -v test_arbitrage_scanner.py
```

`observed_at: "NOW"` is simulation shorthand replaced by each adapter at query time. Fixed ISO timestamps remain supported for reproducible stale-quote tests.

## Units and assets

Checked-in simulation uses WPHRS (18 decimals) as base and USDC (6 decimals) as quote. Addresses are explicit simulation identifiers, not claimed deployments. Every amount uses integer smallest-unit atoms:

- `1 WPHRS = 10^18` WPHRS atoms.
- `1 USDC = 10^6` USDC atoms.
- `trade_size_quote_atoms = 1000000000` means 1,000 USDC.
- `minimum_net_profit_quote_atoms = 5000000` means 5 USDC.

Scanner rejects source asset/address/decimal mismatch and quotes older than `max_quote_age_seconds`.

## Net calculation

For each direction, both constant-product pools (`x*y=k`) calculate amount-aware outputs. Venue fee is applied inside each swap. Cost ledger decomposes result into buy fee, sell fee, CPMM price-impact slippage, and gas:

```text
gross spread = no-fee, no-impact route output - trade input
venue fees = loss attributable to configured per-venue fee_bps
price-impact slippage = remaining loss from reserve movement at requested amount
gas = sum(prepared call gas_limit) * gas_price_quote_atoms_per_unit
net = gross spread - venue fees - price-impact slippage - gas
    = actual two-leg route output - trade input - gas
```

All bps fields require integer `0..10000`. Addresses, timezone-aware quote/scan timestamps, future deadline, amounts, gas values, and reserves are validated before use. Every ABI `uint256` word requires exact integer `0..2^256-1`; positive trade size, reserves, and gas units additionally reject zero. Larger trades produce nonlinear price impact. Gas units come from exact two venue responses and become exact prepared call limits.

## Threshold and preparation

Threshold is strict. Scanner emits `prepared_execution` only when `net > minimum_net_profit_quote_atoms`. Prepared artifact contains two concrete unsigned ABI-encoded `swapExactTokensForTokens` calls, target routers, values, gas limits, call order, atomic simulation semantics, and no signing/broadcast claim. `execute_prepared` runs deterministic atomic simulation; any failed leg returns `SIMULATED_REVERT` with zero completed calls.

Every `scan(...)` attempt appends JSONL, including top-level config validation and calldata encoding errors. Successful route records include source reads, raw provenance, gross spread, full costs, net, and decision; early errors include fields available before rejection. Tests cover malformed addresses, timestamps/deadlines, uint bounds, source failure, stale quotes, asset/decimal mismatch, invalid bps, no-bundle threshold path, and one-leg rollback.

## Scope

Meets Arena wording through allowed simulated execution. Does not prove Atlantic testnet liquidity, real venue integration, allowance handling, nonce handling, transaction signing, or broadcast. Replace adapters and simulation addresses only when verified Atlantic venue quote/router contracts exist.

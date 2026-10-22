# Wallet Risk Checker

Read-only, stdlib-only Pharos wallet screening backed by genuine [Chain MCP](https://mcp.pharos.xyz/mcp) responses. Output is explainable heuristic screening, not a claim that an address is malicious.

## Run

```bash
python3 wallet_risk_checker.py 0xb02627392ff222e997370e0d1d2ab6b846d76b59 --window 20
python3 wallet_risk_checker.py 0x013de7ba7ebd8d186bebf4f08fbd229dfb362906 --window 1 --to-block 20883509
python3 -m unittest -v test_wallet_risk_checker.py
```

`--window` accepts 1–1000 blocks. `--to-block` makes evidence reproducible. `--flagged ADDRESS` is repeatable and only applies user-supplied intelligence; checker never invents a denylist.

## Signals and rules

Every report explains six signals in plain language:

1. contract bytecode presence (`get_code`);
2. native PROS balance (`get_balance`);
3. lifetime outgoing nonce (`get_transaction_count`);
4. recent incoming/outgoing transaction activity (`get_block`);
5. ERC-20 `Approval` frequency and unique spenders (`get_logs`);
6. direct recent interaction with explicitly configured flagged addresses (`get_block`).

Scores:

- +2: EOA has positive balance, recent incoming activity, and zero lifetime outgoing nonce (freshly funded);
- +1: EOA has positive balance and incoming but no outgoing transaction in inspected window;
- +3: at least 3 approvals to at least 2 unique spenders in window;
- +4: direct transaction with configured flagged address;
- low = 0, medium = 1–2, high = 3+.

Code presence is checked, but source-code verification is not labeled: Chain MCP exposes bytecode, not explorer verification metadata. Windowed absence means “not seen in this window,” never “never happened.”

## Genuine evidence

`evidence/wallet-risk-checker.json` records exact Chain MCP observations and command outcomes.

- Clean example `0xb026...6b59`: balance `102253124359823000` wei, nonce `8`, no bytecode, no observed activity/approvals in blocks `20883588–20883607`; low, score 0.
- Risky example `0x013d...2906` at block `20883509`: balance `15586186450076532507` wei, nonce `0`, one incoming transfer in that one-block window, no outgoing transfer, no bytecode; high, score 3. This label follows stated fresh-funding rules only.

Live values change. Historical risky command remains reproducible while RPC retains block state.

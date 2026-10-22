# Pharos Agent Arena Tools

Public, reproducible implementations for Pharos Agent Arena. Each task has its own README, source, tests, evidence, and deployed proof page where submitted.

## Task Index

### Live read-only chain tools

- [Read Contract State](README-arena-contract-state.md) — Pharos mainnet; four USDC reads pinned to one block.
- [Event/Log Monitor](README-arena-event-monitor.md) — Pharos mainnet; persistent filtered event polling and deduplication.
- [Threshold Guardian](README-threshold-guardian.md) — Pharos mainnet; three configurable chain conditions with FIRE/HOLD traces.
- [Dry-Run Executor](README-dry-run-executor.md) — Pharos mainnet; transaction simulation, gas estimate, and fail-closed execution guard.
- [Trend Watcher](README-trend-watcher.md) — Pharos mainnet; persistent observations and configurable trend detection.
- [Whale-Watching Agent](README-whale-watcher.md) — Pharos mainnet; five-address USDC activity summary and significant-move filtering.
- [Wallet Risk Checker](README-wallet-risk-checker.md) — Pharos mainnet; explainable heuristic screening from six on-chain signals.
- [Audit-Log Agent](README-audit-log-agent.md) — Pharos mainnet; date-range activity categories, totals, links, and Markdown export.
- [dApp Support Agent](README-dapp-support-agent.md) — Pharos mainnet; failed-transaction diagnosis from transaction, receipt, and historical replay.

### Docs and multi-tool agents

- [Doc-Search CLI](README-doc-search.md) — sourced natural-language search over Developer Docs MCP.
- [Docs MCP Onboarding](README-docs-mcp-onboarding.md) — first-use log with three concrete documentation gaps and fixes.
- [Skill + Chain MCP Flow](README-skill-chain-mcp-flow.md) — one request moves live data through Chain MCP and the Pharos Skill Engine read procedure.
- [Docs MCP + Chain MCP Agent](README-docs-chain-mcp-agent.md) — explains two functions from docs, calls them on chain, and interprets results.
- [Doc-Grounded Builder](README-doc-grounded-builder.md) — cited plans before Chain MCP execution for three read-only requests.

### Policy and unsigned preparation

- [Policy Gatekeeper](README-policy-gatekeeper.md) — spend, allowlist, and time-window rules with append-only audit decisions.
- [Natural-Language Payment Agent](README-natural-language-payment-agent.md) — Atlantic testnet live validation and unsigned wallet request only.
- [Invoice-to-Payment Agent](README-invoice-payment-agent.md) — Atlantic testnet invoice parsing and unsigned native-payment payload with reference data.
- [Batch Executor](README-batch-executor.md) — Pharos mainnet Multicall3 simulation with tolerant and strict failure evidence.

### Explicit simulation

- [Arbitrage Scanner](README-arbitrage-scanner.md) — two independent simulated venue adapters, amount-aware costs, threshold gating, and unsigned two-leg bundle. No live venue claim.

### Delivery agents

- [On-Chain Alert Bot](README-alert.md) — verified Telegram delivery, durable event-ID suppression, and sanitized public evidence.

## Verification

```bash
python3 -m compileall -q .
python3 -m unittest discover -v
```

Current full suite: 72 tests. Python standard library is used unless a documented system CLI is required.

## Evidence Rules

- Live observations name network, chain ID, block, and source.
- Deterministic fixtures are labelled as simulation and never presented as live data.
- Unsigned preparation tools never request private keys, sign, or broadcast.
- Gas estimates are observations, not paid gas or benchmarks.
- Public evidence contains no credentials.

## Public Links

- Repository: https://github.com/flxthesixth/pharos-arena-chain-mcp
- Proof site: https://pharos-contract-state.pages.dev/

Task submission and reviewer approval are separate from repository implementation. README and evidence files do not imply awarded points.

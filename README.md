# Pharos Chain MCP examples

Two small read-only Python scripts for Pharos Agent Arena. They query [Pharos Chain MCP](https://mcp.pharos.xyz/mcp) without a wallet or third-party Python packages.

- [Read Contract State](README-arena-contract-state.md): fetch four values from the mainnet USDC contract at one block.
- [Event/Log Monitor](README-arena-event-monitor.md): poll USDC `Transfer` logs, decode new events, and save a local cursor.

```bash
python3 arena_contract_state.py --self-test
python3 arena_contract_state.py
python3 arena_event_monitor.py --self-test
python3 arena_event_monitor.py --interval 15
```

Python 3.9+ and HTTPS access required. Chain ID is checked before queries. No transactions or task submissions are made by these scripts.

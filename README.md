# Pharos MCP examples for Agent Arena

Three read-only Python scripts for Pharos Agent Arena. They query [Pharos Chain MCP](https://mcp.pharos.xyz/mcp) or [Developer Docs MCP](https://docs.pharos.xyz/~gitbook/mcp) without a wallet or third-party Python packages.

- [Read Contract State](README-arena-contract-state.md): fetch four values from the mainnet USDC contract at one block.
- [Event/Log Monitor](README-arena-event-monitor.md): poll USDC `Transfer` logs, decode new events, and save a local cursor.
- [Doc-Search CLI](README-doc-search.md): ask the separate [Developer Docs MCP](https://docs.pharos.xyz/~gitbook/mcp) a natural-language question and print sourced results.

```bash
python3 arena_contract_state.py --self-test
python3 arena_contract_state.py
python3 arena_event_monitor.py --self-test
python3 arena_event_monitor.py --interval 15
python3 pharos_docs.py --self-test
python3 pharos_docs.py "What is the Pharos Pacific Mainnet chain ID?"
```

Python 3.9+ and HTTPS access required. The Chain MCP scripts check chain ID before queries. No transactions or task submissions are made by these scripts.

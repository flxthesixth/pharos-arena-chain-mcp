# Pharos MCP examples for Agent Arena

Four read-only Python scripts for Pharos Agent Arena. They query [Pharos Chain MCP](https://mcp.pharos.xyz/mcp) or [Developer Docs MCP](https://docs.pharos.xyz/~gitbook/mcp) without a wallet or third-party Python packages.

- [Read Contract State](README-arena-contract-state.md): fetch four values from the mainnet USDC contract at one block.
- [Event/Log Monitor](README-arena-event-monitor.md): poll USDC `Transfer` logs, decode new events, and save a local cursor.
- [Doc-Search CLI](README-doc-search.md): ask the separate [Developer Docs MCP](https://docs.pharos.xyz/~gitbook/mcp) a natural-language question and print sourced results.
- [On-Chain Alert Bot](README-alert.md): filter USDC transfers and send qualifying events to a configured Discord webhook. Real-channel delivery is not yet verified.
- [Doc-Grounded Builder Agent](README-doc-grounded-builder.md): plan three read-only how-do-I requests from cited Docs MCP answers, execute with Chain MCP, and verify results.

```bash
python3 arena_contract_state.py --self-test
python3 arena_contract_state.py
python3 arena_event_monitor.py --self-test
python3 arena_event_monitor.py --interval 15
python3 pharos_docs.py --self-test
python3 pharos_docs.py "What is the Pharos Pacific Mainnet chain ID?"
python3 pharos_alert.py --self-test
python3 -m unittest -v test_doc_grounded_builder.py
python3 doc_grounded_builder.py "How do I check the Pharos chain ID?"
# For real Discord delivery, see README-alert.md.
```

Python 3.9+ and HTTPS access required. The Chain MCP scripts check chain ID before queries. No transactions or task submissions are made by these scripts.

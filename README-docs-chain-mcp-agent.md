# Docs MCP + Chain MCP Agent

Read-only agent asks live [Pharos Docs MCP](https://docs.pharos.xyz/~gitbook/mcp) what ERC-20 `decimals()` and `totalSupply()` mean, requires source URLs in each answer, then calls those same functions through live [Pharos Chain MCP](https://mcp.pharos.xyz/mcp). It interprets `totalSupply()` using returned `decimals()`.

Target: Pharos mainnet USDC [`0xc879c018db60520f4355c26ed1a6d572cdac1815`](https://www.pharosscan.xyz/address/0xc879c018db60520f4355c26ed1a6d572cdac1815), chain ID 1672. No wallet, key, transaction, or third-party Python package.

## Run

```bash
python3 docs_chain_mcp_agent.py --self-test
python3 docs_chain_mcp_agent.py
python3 docs_chain_mcp_agent.py --output evidence/docs-chain-mcp-agent.json
```

Python 3.9+ and outbound HTTPS required.

## Flow

1. `askQuestion` on Docs MCP explains `decimals()` and supplies Pharos docs URLs.
2. `askQuestion` on Docs MCP explains `totalSupply()` and supplies Pharos docs URLs.
3. Chain MCP `get_chain_info` selects one live mainnet block.
4. Chain MCP `eth_call` invokes selectors `0x313ce567` and `0x18160ddd` at that block.
5. Agent ABI-decodes both integers and computes `totalSupply / 10^decimals`.

## Fresh evidence

`evidence/docs-chain-mcp-agent.json` records complete Docs MCP answers, exact queries and sources, Chain MCP raw values, decoded values, interpretations, contract, and block. Latest validated run at block `20883043` returned:

- `decimals()` = `6`: one displayed USDC is `10^6` raw units.
- `totalSupply()` = `48198725756925` raw units: `48198725.756925 USDC` after applying 6 decimals.

Live supply and block change over time.

# Skill + Chain MCP Flow — Pharos Agent Arena

One user request moves live data through two independent Pharos tools:

```text
User request
  |
  v
Chain MCP
  - verify chain ID 1672
  - select latest block
  - call USDC decimals() at that block
  |
  | contract + fixed block + decoded value
  v
Pharos Skill Engine: Read Contract procedure
  - use its documented cast call template
  - call decimals()(uint8) on the same contract and block
  |
  v
Compare outputs and report verified interpretation
```

The Skill Engine procedure comes from the installed trusted `pharos-skill-engine` skill, `references/query.md`, section **Contract Read-Only Call**. Its output depends on the live contract and block returned by Chain MCP in the same run.

## Run

```bash
python3 skill_chain_mcp_flow.py --self-test
python3 skill_chain_mcp_flow.py \
  "verify the live USDC decimals through Chain MCP and Skill Engine"
```

Requirements: Python 3.9+, Foundry `cast`, outbound HTTPS. No wallet, private key, signing, or transaction is used.

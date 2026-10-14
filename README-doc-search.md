# Doc-Search CLI — Pharos Agent Arena

A small read-only CLI for the [Pharos Developer Docs MCP](https://docs.pharos.xyz/~gitbook/mcp). It calls `askQuestion` and prints the answer with up to three document links returned by the server. It does not call the write-capable `sendFeedback` tool.

## Install and run

Python 3.9+ and outbound HTTPS are required. No packages or API keys are needed. From this repository:

```bash
python3 pharos_docs.py --self-test
python3 pharos_docs.py "What is the chain ID and RPC URL of Pharos Pacific Mainnet?"
```

Use quotes around multiword questions. If the docs server cannot answer, the CLI says so instead of printing a guessed answer. Source links come from Docs MCP; they are not independent fact checks.

## Three live queries

Output was observed from Developer Docs MCP; its answer and citation order can change.

```text
$ python3 pharos_docs.py 'What is the chain ID and RPC URL of Pharos Pacific Mainnet?'
Pharos Pacific Mainnet uses:

* **Chain ID:** `1672`
* **RPC URL:** `https://rpc.pharos.xyz`

See [Pacific Mainnet](/getting-started/network/pacific-mainnet).

Sources:
- https://docs.pharos.xyz/getting-started/network/pacific-mainnet
- https://docs.pharos.xyz/node-and-validator-guide/pharos-network-snapshots
- https://docs.pharos.xyz/tooling-and-infrastructure/rpc/zan
```

```text
$ python3 pharos_docs.py 'What is the chain ID and RPC URL of Atlantic Testnet?'
Atlantic Testnet uses **chain ID `688689`** and RPC URL **`https://atlantic.dplabs-internal.com`**. See [Atlantic Testnet](/getting-started/network/atlantic-testnet).

Sources:
- https://docs.pharos.xyz/getting-started/network/atlantic-testnet
- https://docs.pharos.xyz/node-and-validator-guide/node-management
- https://docs.pharos.xyz/tooling-and-infrastructure/rpc/zan
```

```text
$ python3 pharos_docs.py 'How do I raise purple dragons on Pharos using jellybeans?'
No good answer found in Pharos docs. Try a more specific question.
```

This is a local build and test, not proof of Arena submission or reviewer acceptance.

# Doc-Grounded Builder Agent

Read-only Pharos Agent Arena implementation. Every request follows one flow:

1. Ask Developer Docs MCP and require `docs.pharos.xyz` citations.
2. Record a concrete read-only plan before chain access.
3. Execute the mapped tool through hosted Chain MCP.
4. Verify returned fields against plan invariants.
5. Report `success` or `failure`. Unknown requests report `unsupported`; Chain MCP is not called.

No wallet, key, transaction, signature, or third-party Python package is used.

## Supported requests

```bash
python3 doc_grounded_builder.py "How do I check the Pharos chain ID?"
python3 doc_grounded_builder.py "How do I get the latest block number?"
python3 doc_grounded_builder.py "How do I read native balance for 0x0000000000000000000000000000000000000000?"
```

Mappings:

| Request | Docs-grounded method | Chain MCP tool | Verification |
|---|---|---|---|
| Chain ID | `eth_chainId` | `get_chain_info` | hexadecimal and decimal IDs agree; configured chain matches |
| Latest block | `eth_blockNumber` | `get_block_number` | hexadecimal and decimal heights agree; height is non-negative |
| Native balance | `eth_getBalance` | `get_balance` | address, hexadecimal wei, decimal wei, and 18-decimal PROS value agree |

Balance requests require an explicit 20-byte EVM address. All chain operations are read-only and output `requires_signature: false`.

## Unsupported request

```bash
python3 doc_grounded_builder.py "How do I deploy a Solana program with Anchor?"
```

Result is `status: "unsupported"` and: `Pharos docs have no coverage for this request; no action was improvised.` `execution` is `null`.

## Tests

```bash
python3 -m unittest -v test_doc_grounded_builder.py
```

Five tests cover three successful flows, unsupported no-action behavior, and fail-closed behavior when Docs MCP returns no citations.

## Live evidence

Captured by running commands above against Developer Docs MCP and hosted Chain MCP:

- `evidence/doc-grounded-builder/chain-id.json`
- `evidence/doc-grounded-builder/latest-block.json`
- `evidence/doc-grounded-builder/native-balance.json`
- `evidence/doc-grounded-builder/unsupported.json`

Each supported artifact contains Docs MCP answer and source URLs, plan, exact Chain MCP tool/result, and verification checks. Values are observations at run time, not fixtures.

# Invoice-to-Payment Agent

This stdlib-only CLI extracts and validates two invoice formats, then builds an unsigned native-PHRS payment transaction for Pharos Atlantic Testnet (`chainId` 688689). It never signs or broadcasts.

## Demo

```bash
python3 -m unittest -v test_invoice_payment_agent.py
python3 invoice_payment_agent.py samples/invoice.json --expect samples/expected.json
python3 invoice_payment_agent.py samples/invoice.txt
```

Supported formats:

- strict JSON object with `payee`, `amount`, `currency`, `reference`
- text lines: `Pay to:`, `Total: <amount> <currency>`, `Reference:`

Missing fields, duplicate conflicts, malformed addresses or amounts, unsupported currencies, and mismatches against an optional expected record block output. Blocked reports contain no transaction. When no expected record is supplied, output says `{"checked": false, "match": null}` rather than implying a failed comparison. Both JSON and text inputs use the same mismatch check.

## Provenance

For each successful run, the agent first calls `eth_chainId` and requires Atlantic chain ID `688689` before trusting block or code data. It then calls `eth_blockNumber`, followed by `eth_getCode` with that exact block number, and reads the block timestamp. Output records RPC endpoint, network, chain ID, block number, timestamp, and a reproducible `cast code` command. `code_at_block: empty` means only that RPC returned no deployed bytecode at the pinned block; it does not prove that the address is an EOA.

## Honest reference transport

The agent supports native `PHRS` only. When the pinned code result is empty, the transaction sends native value and stores the UTF-8 invoice reference as raw bytes in transaction `data`. Raw calldata is compatible with a no-code recipient because no contract executes or decodes it at that block. Wallets and indexers may preserve or display the bytes, but no protocol-level invoice field or recipient-side decoding is implied.

Decode the generated raw calldata with this safe, local stdlib command (replace the sample hex as needed):

```bash
python3 -c 'import sys; print(bytes.fromhex(sys.argv[1].removeprefix("0x")).decode("utf-8"))' 0x41544c2d494e562d323032362d303031
```

Standard ERC-20 `transfer(address,uint256)` has no reference parameter. The agent rejects token invoices instead of pretending appended bytes carry a reference or targeting an unverified router. Contract payees are rejected because arbitrary calldata could invoke fallback logic. Add token payments only after identifying and verifying a deployed Atlantic payment contract with explicit reference semantics.

## Safety and limits

- Network fixed to Atlantic Testnet, RPC `https://atlantic.dplabs-internal.com`.
- Only plain positive decimal amounts with at most 18 fractional digits.
- Reference capped at 128 UTF-8 bytes.
- Sample addresses and invoices contain no secrets.
- No key input, signing dependency, or broadcast path exists.

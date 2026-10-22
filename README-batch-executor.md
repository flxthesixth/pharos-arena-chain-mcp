# Batch Executor — Pharos Agent Arena

Stdlib-only Python CLI accepts 3 or more independent read calls and ABI-encodes one prepared `Multicall3.aggregate3((address,bool,bytes)[])` transaction. It simulates with `eth_call`, observes batch and hypothetical separate-call gas estimates, and never signs or broadcasts.

Target is canonical Multicall3 deployment `0xcA11bde05977b3631167028862bE2a173976CA11` on Pharos mainnet (chain ID 1672). Live checks confirmed deployed bytecode and `getChainId() == 1672`.

## Run

```bash
python3 -m unittest -v test_batch_executor.py
python3 batch_executor.py @batch-actions.json
python3 batch_executor.py @batch-actions-partial-failure.json
python3 batch_executor.py @batch-actions-strict-failure.json
```

Action schema:

```json
{"label":"read block number","target":"0xca11bde05977b3631167028862be2a173976ca11","allow_failure":false,"data":"0x42cbb15c"}
```

`target` and `data` are required. `label` defaults to `action-N`; `allow_failure` defaults to `false`. Native value is deliberately unsupported because `aggregate3` has no per-call value field; use `aggregate3Value` when value-bearing calls become required.

## Live evidence

Every run first pins one block, then verifies nonempty Multicall3 bytecode and `getChainId() == 1672` at that block. All simulation and estimate RPCs use same block number. Evidence records UTC observation time, endpoint, exact command, block number/hash/timestamp, code size/SHA-256, and observed Multicall3 chain ID.

`evidence/batch-executor.json` records one simulated prepared transaction containing 3 successful independent read calls:

- Batch: 1 hypothetical transaction step, `eth_estimateGas` observation 40,739.
- Separate: 3 hypothetical transactions, summed `eth_estimateGas` observations 86,234.
- Difference: 2 steps (66.67%) and 45,495 estimated gas units.
- `broadcast: false`: no signing or submission path exists.

Gas values are observations at one pinned block, not paid gas and not a benchmark. Separate-transaction comparison is hypothetical; only independent read calls were simulated.

`evidence/batch-executor-partial-failure.json` proves tolerant failure behavior: action index 1 uses unsupported selector `0xdeadbeef` with `allow_failure: true`; result is `success: false`, while actions 0 and 2 succeed.

`evidence/batch-executor-strict-failure.json` proves strict failure behavior against live RPC: same unsupported selector with `allow_failure: false` makes aggregate `eth_call` revert. CLI exits `2`, emits structured failure on stderr, sets `prepared_success: false`, and omits `prepared_transaction`.

## Partial failure semantics

These semantics come from selected Multicall3 `aggregate3` contract:

- `allow_failure: true`: failed subcall returns `(false, returnData)`; loop continues to later read calls.
- `allow_failure: false`: failed subcall makes `aggregate3` revert. A hypothetical submitted transaction would be atomic and roll back every action; this CLI only simulates reads.
- A reverted strict batch produces RPC simulation error rather than a result array. CLI exits nonzero and does not broadcast.

Individual gas can be unavailable for a reverting action. In that case report keeps step comparison but sets individual total and gas saving to `null`; it does not invent a gas value.

Network timeout, malformed JSON, missing RPC result, malformed ABI data, and out-of-bounds ABI offsets fail closed with structured stderr and nonzero exit.

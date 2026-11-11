# read-contract-state

[Task index](../README.md) · [Legacy instructions](../../README-arena-contract-state.md) · [Original proof](../../docs/index.html)

Canonical [source](source/arena_contract_state.py) retains embedded offline `self_test()`; no test copies.
Legacy root imports and CLI remain supported. Relative files resolve against caller working directory.
Original evidence, proof URLs, and legacy instructions stay unchanged; no evidence regenerated.

## Offline checks

From repository root:

```bash
python3 arena_contract_state.py --self-test
python3 tasks/read-contract-state/source/arena_contract_state.py --self-test
python3 -m unittest -v test_task_layout.py
```

From this task folder: `python3 source/arena_contract_state.py --self-test`.
Without `--self-test`, commands use live read-only MCP; migration checks make no external requests.
No submission, awarded points, or reviewer approval implied.

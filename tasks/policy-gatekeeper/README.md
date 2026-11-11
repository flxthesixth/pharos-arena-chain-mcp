# Policy Gatekeeper

[Task index](../README.md) · [Legacy instructions](../../README-policy-gatekeeper.md) · [Video](../../videos/README.md#policy-gatekeeper)

Canonical [source](source/policy_gatekeeper.py), [tests](tests/test_policy_gatekeeper.py), and [evidence index](evidence/README.md).
Tests link to existing root suite; submitted evidence and proof paths stay unchanged.

## Root commands

```bash
python3 -m unittest -v test_policy_gatekeeper.py
python3 -m unittest -v test_task_layout.py
```

## From this task folder

```bash
PYTHONPATH=../.. python3 -m unittest discover -s tests -v
python3 source/policy_gatekeeper.py '{"action":"transfer","asset":"USDC","amount":"25","to":"0x1111111111111111111111111111111111111111","requested_at":"2026-10-22T12:00:00Z"}' --policy ../../policy-gatekeeper.json --audit /tmp/policy-gatekeeper-demo.jsonl
```

Batch command above (where applicable) makes read-only RPC calls; tests are offline.
Policy command writes only unsigned decisions to specified local audit file.
All relative inputs and audit outputs still resolve against caller working directory, never source directory.
Legacy root entrypoints, config/sample paths, imports, and proof pages remain supported.
Batch evidence command labeling remains legacy `python3 batch_executor.py`; no historical evidence is regenerated.

## Submission boundary

Owner-verified submission: APPROVED, 50 points. This is not verification of video bonus.
Catalog point values/status are historical task metadata, not awarded points or current submission status.

# Policy Gatekeeper — Pharos Agent Arena

Stdlib-only Python gate checks every transaction intent against spend-limit, destination-allowlist, and time-window rules. Every result names deciding rule and is appended to durable JSON Lines audit log. Denied requests never reach preparation callback. Allowed requests produce inert, unsigned, unbroadcast transaction intent only; script has no signing, wallet, RPC, or broadcast path.

## Files

- `policy-gatekeeper.json` — three policy rule types.
- `policy_gatekeeper.py` — validation, decision, append-only audit, prepare-only CLI.
- `test_policy_gatekeeper.py` — allow case, one deny per rule, denied-callback checks, invalid input, audit persistence.

## Run

Python 3.9+; no third-party packages.

```bash
python3 -m unittest -v test_policy_gatekeeper.py
python3 policy_gatekeeper.py \
  '{"action":"transfer","asset":"USDC","amount":"25","to":"0x1111111111111111111111111111111111111111","requested_at":"2026-10-22T12:00:00Z"}'
```

Default config: `policy-gatekeeper.json`. Default audit: `policy-gatekeeper-audit.jsonl`. Override with `--policy` and `--audit`.

## Decision behavior

Rules run in config order: `spend_limit`, `allowlist`, `time_window`. First failed rule decides denial. Malformed requests deny under `invalid_request`. Passing all rules returns `allow` with `all_rules_passed`, then calls prepare-only function. Time-window start is inclusive; end is exclusive. Overnight windows are supported. Request timestamps must include UTC offset or `Z`.

Audit records include timestamp, complete request, decision, deciding rule, and reason. File opens with OS append mode for each decision and calls `fsync` before any allowed preparation. Existing records are never rewritten by application.

## Deny examples

```bash
# spend_limit
python3 policy_gatekeeper.py '{"action":"transfer","asset":"USDC","amount":"101","to":"0x1111111111111111111111111111111111111111","requested_at":"2026-10-22T12:00:00Z"}'

# allowlist
python3 policy_gatekeeper.py '{"action":"transfer","asset":"USDC","amount":"25","to":"0x3333333333333333333333333333333333333333","requested_at":"2026-10-22T12:00:00Z"}'

# time_window
python3 policy_gatekeeper.py '{"action":"transfer","asset":"USDC","amount":"25","to":"0x1111111111111111111111111111111111111111","requested_at":"2026-10-22T18:00:00Z"}'
```

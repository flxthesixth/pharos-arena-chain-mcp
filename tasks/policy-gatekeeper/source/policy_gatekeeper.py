"""Policy gate for safe, unsigned transaction preparation."""
import argparse
import json
import os
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

RULES = ("spend_limit", "allowlist", "time_window")


def load_policy(path):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or any(rule not in policy for rule in RULES):
        raise ValueError("policy must define spend_limit, allowlist, and time_window")
    spend = policy["spend_limit"]
    allowlist = policy["allowlist"]
    window = policy["time_window"]
    try:
        limit = Decimal(spend["max_amount"])
        addresses = allowlist["addresses"]
        zone = ZoneInfo(window["timezone"])
        start = time.fromisoformat(window["start"])
        end = time.fromisoformat(window["end"])
    except (KeyError, TypeError, InvalidOperation, ZoneInfoNotFoundError) as error:
        raise ValueError(f"invalid policy: {error}") from error
    if not limit.is_finite() or limit < 0:
        raise ValueError("spend limit must be a finite non-negative number")
    if not isinstance(spend.get("asset"), str) or not spend["asset"]:
        raise ValueError("spend_limit.asset must be a non-empty string")
    if not isinstance(addresses, list) or not addresses or not all(_address(a) for a in addresses):
        raise ValueError("allowlist.addresses must contain valid EVM addresses")
    if start == end:
        raise ValueError("time window start and end must differ")
    return {"spend_limit": {"asset": spend["asset"], "max_amount": limit},
            "allowlist": {"addresses": {a.lower() for a in addresses}},
            "time_window": {"timezone": zone, "start": start, "end": end}}


def _address(value):
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        return False
    try:
        int(value[2:], 16)
    except ValueError:
        return False
    return True


def _audit_append(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Gatekeeper:
    def __init__(self, policy, audit_path):
        self.policy = policy
        self.audit_path = Path(audit_path)

    def decide(self, request):
        try:
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            amount = Decimal(request["amount"])
            asset = request["asset"]
            destination = request["to"]
            requested_at = datetime.fromisoformat(request["requested_at"].replace("Z", "+00:00"))
            if (not amount.is_finite() or amount < 0 or not isinstance(asset, str)
                    or not _address(destination) or requested_at.tzinfo is None):
                raise ValueError("invalid field value")
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            return "deny", "invalid_request", str(error)

        spend = self.policy["spend_limit"]
        if asset != spend["asset"] or amount > spend["max_amount"]:
            return "deny", "spend_limit", (
                f"amount must not exceed {spend['max_amount']} {spend['asset']}")
        if destination.lower() not in self.policy["allowlist"]["addresses"]:
            return "deny", "allowlist", "destination is not allowlisted"
        window = self.policy["time_window"]
        local_time = requested_at.astimezone(window["timezone"]).timetz().replace(tzinfo=None)
        start, end = window["start"], window["end"]
        inside = start <= local_time < end if start < end else local_time >= start or local_time < end
        if not inside:
            return "deny", "time_window", f"request is outside {start}-{end} {window['timezone'].key}"
        return "allow", "all_rules_passed", "all policy rules passed"

    def handle(self, request, prepare):
        decision, rule, reason = self.decide(request)
        result = {"decision": decision, "deciding_rule": rule, "reason": reason}
        _audit_append(self.audit_path, {
            "recorded_at": datetime.now().astimezone().isoformat(),
            "decision": decision, "deciding_rule": rule, "reason": reason,
            "request": request,
        })
        if decision == "allow":
            result["prepared"] = prepare(request)
        return result


def prepare_only(request):
    """Return inert transaction intent; never sign or broadcast."""
    return {"status": "prepared", "transaction": {
        "action": request.get("action"), "asset": request["asset"],
        "amount": request["amount"], "to": request["to"]},
        "signed": False, "broadcast": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request", help="request JSON object")
    parser.add_argument("--policy", type=Path, default=Path("policy-gatekeeper.json"))
    parser.add_argument("--audit", type=Path, default=Path("policy-gatekeeper-audit.jsonl"))
    args = parser.parse_args()
    try:
        request = json.loads(args.request)
        result = Gatekeeper(load_policy(args.policy), args.audit).handle(request, prepare_only)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

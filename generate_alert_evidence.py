"""Send one explicit Arena demo alert from a public event JSON."""
import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from pharos_alert import configured_sender, deliver_once, event_id, load_state

HASH = re.compile(r"0x[0-9a-fA-F]{64}\Z")
ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}\Z")


def validate_event(event):
    required = {"amount", "from", "to", "block", "tx_hash", "log_index"}
    if not required <= event.keys() or not HASH.fullmatch(str(event["tx_hash"])):
        raise ValueError("event must contain genuine public transaction fields")
    if not ADDRESS.fullmatch(str(event["from"])) or not ADDRESS.fullmatch(str(event["to"])):
        raise ValueError("invalid event address")
    try:
        amount = Decimal(str(event["amount"]))
        block, log_index = int(event["block"]), int(event["log_index"])
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid event value or index") from None
    if not amount.is_finite() or amount < 0 or block < 0 or log_index < 0:
        raise ValueError("event values must be finite and nonnegative")
    return {**event, "amount": str(amount), "block": block, "log_index": log_index}


def run(event_path, state_path, evidence_path):
    event = validate_event(json.loads(event_path.read_text()))
    state = load_state(state_path, event["block"])
    key = event_id(event)
    if key in state["outbox"]:
        raise RuntimeError("demo event already attempted; refusing repeat delivery")
    send = configured_sender()
    if not deliver_once(event, state, state_path, Decimal("0"), send,
                        label="ARENA DEMO — Pharos On-Chain Alert"):
        raise RuntimeError("demo event was not delivered")
    receipt = state["outbox"][key]["receipt"]
    evidence = {"demo": True, "event_id": key, "tx_url": f"https://www.pharosscan.xyz/tx/{event['tx_hash']}",
                "value": f"{event['amount']} USDC", "receipt": receipt}
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=Path, help="Genuine public decoded Transfer event JSON")
    parser.add_argument("--state", type=Path, default=Path("alert-demo-state.json"))
    parser.add_argument("--evidence", type=Path, default=Path("evidence/on-chain-alert-delivery.json"))
    args = parser.parse_args()
    evidence = run(args.event, args.state, args.evidence)
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()

"""Send thresholded Pharos USDC Transfer alerts to Telegram or Discord."""
import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from arena_event_monitor import CONTRACT, TRANSFER, decode, post, tool

EXPLORER = "https://www.pharosscan.xyz/tx/"


class DeliveryError(RuntimeError):
    """Channel rejected or could not confirm delivery."""


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w") as output:
        output.write(json.dumps(state, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temp, path)


def new_state(block):
    return {"version": 2, "cursor": {"block": block, "log_index": -1}, "outbox": {}}


def load_state(path, initial_block=None):
    if not path.exists():
        if initial_block is None:
            raise ValueError("initial block required for new state")
        return new_state(initial_block)
    state = json.loads(path.read_text())
    if "cursor" not in state:  # migrate original cursor-only format
        state = {"version": 2, "cursor": state, "outbox": {}}
    if not isinstance(state.get("cursor"), dict) or not isinstance(state.get("outbox"), dict):
        raise ValueError("Invalid alert state")
    return state


def event_id(event):
    return f"{event['tx_hash'].lower()}:{int(event['log_index'])}"


def format_alert(event, label="Pharos On-Chain Alert"):
    return (f"{label} — USDC Transfer\n"
            f"What happened: {event['from']} sent {event['to']}\n"
            f"Value: {event['amount']} USDC\nBlock: {event['block']}\n"
            f"Transaction: {EXPLORER}{event['tx_hash']}")


def alert(event, threshold, send, label="Pharos On-Chain Alert"):
    if Decimal(event["amount"]) < threshold:
        return None
    return send(format_alert(event, label))


def mask_chat_id(chat_id):
    value = str(chat_id)
    return "*" * max(0, len(value) - 4) + value[-4:]


def telegram_sender(token, chat_id, opener=urlopen):
    if not token or not chat_id:
        raise ValueError("Telegram token and chat ID are required")
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def send(text):
        request = Request(url, json.dumps({"chat_id": chat_id, "text": text,
                                           "disable_web_page_preview": True}).encode(),
                          {"Content-Type": "application/json"}, method="POST")
        try:
            with opener(request, timeout=20) as response:
                status = response.status
                body = response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            status = getattr(exc, "code", "network")
            raise DeliveryError(f"Telegram delivery failed: HTTP {status}") from None
        if status != 200:
            raise DeliveryError(f"Telegram delivery failed: HTTP {status}")
        try:
            payload = json.loads(body)
            if payload.get("ok") is not True:
                raise DeliveryError("Telegram delivery failed: API rejected request")
            result = payload["result"]
            message_id = int(result["message_id"])
            returned_chat_id = str(result["chat"]["id"])
            if returned_chat_id != str(chat_id):
                raise DeliveryError("Telegram delivery failed: response chat ID mismatch")
            if result.get("text") != text:
                raise DeliveryError("Telegram delivery failed: response text mismatch")
            masked_chat_id = mask_chat_id(returned_chat_id)
            delivered_at = datetime.fromtimestamp(int(result["date"]), timezone.utc).isoformat().replace("+00:00", "Z")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError, OverflowError):
            raise DeliveryError("Telegram delivery failed: invalid API response") from None
        return {"platform": "telegram", "chat_id": masked_chat_id,
                "message_id": message_id, "delivered_at": delivered_at,
                "content_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "response_chat_matches": True, "response_text_matches": True,
                "http_success": True, "api_success": True}
    return send


def webhook_sender(url, opener=urlopen):
    allowed = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
    if not url.startswith(allowed):
        raise ValueError("DISCORD_WEBHOOK_URL must be a Discord HTTPS webhook URL")

    def send(text):
        request = Request(url + ("&" if "?" in url else "?") + "wait=true",
                          json.dumps({"content": text}).encode(),
                          {"Content-Type": "application/json"}, method="POST")
        try:
            with opener(request, timeout=20) as response:
                status, body = response.status, response.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            raise DeliveryError(f"Discord delivery failed: HTTP {getattr(exc, 'code', 'network')}") from None
        if status != 200:
            raise DeliveryError(f"Discord delivery failed: HTTP {status}")
        try:
            message = json.loads(body)
            message_id = str(message["id"])
            channel_id = str(message["channel_id"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise DeliveryError("Discord delivery failed: invalid API response") from None
        return {"platform": "discord", "chat_id": mask_chat_id(channel_id),
                "message_id": message_id, "delivered_at": now(),
                "http_success": True, "api_success": True}
    return send


def deliver_once(event, state, state_path, threshold, send, label="Pharos On-Chain Alert"):
    if Decimal(event["amount"]) < threshold:
        return False
    key = event_id(event)
    if key in state["outbox"]:
        return False
    state["outbox"][key] = {"status": "pending", "created_at": now()}
    save(state_path, state)
    try:
        receipt = send(format_alert(event, label))
    except Exception as exc:
        state["outbox"][key] = {
            "status": "delivery_uncertain",
            "created_at": state["outbox"][key]["created_at"],
            "updated_at": now(),
            "error_type": type(exc).__name__,
            "manual_reconciliation_required": True,
        }
        save(state_path, state)
        raise
    if not isinstance(receipt, dict):
        receipt = {"platform": "custom", "delivered_at": now(),
                   "http_success": True, "api_success": True}
    state["outbox"][key] = {"status": "delivered", "receipt": receipt}
    save(state_path, state)
    return True


def process(session, state, state_path, threshold, send, max_blocks=100):
    cursor = state["cursor"]
    latest = int(tool("get_block_number", {}, session)["blockNumber"])
    start = cursor["block"]
    if start > latest:
        return 0
    end = min(latest, start + max_blocks - 1)
    result = tool("get_logs", {"address": CONTRACT, "topics": [TRANSFER],
                               "fromBlock": hex(start), "toBlock": hex(end)}, session)
    logs = result.get("logs") if isinstance(result, dict) else result
    if not isinstance(logs, list):
        raise ValueError("Unexpected MCP logs response")
    unique = {(log["transactionHash"].lower(), int(log["logIndex"], 16)): log
              for log in logs if not log.get("removed")}
    events = sorted((decode(log) for log in unique.values()),
                    key=lambda item: (item["block"], item["log_index"]))
    sent = 0
    for event in events:
        if (event["block"], event["log_index"]) < (cursor["block"], cursor["log_index"]):
            continue
        sent += deliver_once(event, state, state_path, threshold, send)
        cursor.update(block=event["block"], log_index=event["log_index"] + 1)
        save(state_path, state)
    cursor.update(block=end + 1, log_index=-1)
    save(state_path, state)
    return sent


def configured_sender():
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return telegram_sender(token, chat_id)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if webhook:
        return webhook_sender(webhook)
    raise ValueError("set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or DISCORD_WEBHOOK_URL")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-usdc", default="100", help="Minimum transfer value in USDC")
    parser.add_argument("--state", type=Path, default=Path("alert-state.json"))
    parser.add_argument("--backfill", type=int, default=10)
    parser.add_argument("--interval", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    try:
        minimum = Decimal(args.min_usdc)
    except InvalidOperation:
        parser.error("--min-usdc must be a number")
    if not minimum.is_finite() or minimum < 0 or args.backfill < 1 or args.interval < 1:
        parser.error("threshold must be finite and nonnegative; backfill and interval must be positive")
    try:
        send = configured_sender()
    except ValueError as exc:
        parser.error(str(exc))
    _, session = post("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "pharos-alert", "version": "2.0"}})
    if not session:
        raise RuntimeError("MCP session missing")
    chain = tool("get_chain_info", {}, session)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    state = load_state(args.state, max(0, int(chain["latestBlock"]) - args.backfill + 1))
    while True:
        count = process(session, state, args.state, minimum, send)
        print(f"Delivered {count} alerts", flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()

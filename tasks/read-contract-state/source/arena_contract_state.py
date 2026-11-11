"""Read live Pharos USDC state through the hosted Chain MCP. No wallet or signing."""
import json
from urllib.request import Request, urlopen

ENDPOINT = "https://mcp.pharos.xyz/mcp"
CONTRACT = "0xc879c018db60520f4355c26ed1a6d572cdac1815"
SELECTORS = {"name": "0x06fdde03", "symbol": "0x95d89b41", "decimals": "0x313ce567", "totalSupply": "0x18160ddd"}


def exchange(method, params, session=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    request = Request(ENDPOINT, json.dumps(payload).encode(), headers, method="POST")
    with urlopen(request, timeout=20) as response:
        body = response.read().decode()
        new_session = response.headers.get("Mcp-Session-Id")
    if body.startswith("event: message\n"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    result = json.loads(body)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["result"], new_session


def text(result):
    if result.get("isError"):
        raise RuntimeError(result["content"])
    return json.loads(next(part["text"] for part in result["content"] if part["type"] == "text"))


def decode_string(raw):
    data = bytes.fromhex(raw.removeprefix("0x"))
    offset = int.from_bytes(data[:32], "big")
    size = int.from_bytes(data[offset:offset + 32], "big")
    if offset + 32 + size > len(data):
        raise ValueError("Invalid ABI string")
    return data[offset + 32:offset + 32 + size].decode("utf-8")


def snapshot(call=exchange):
    _, session = call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                      "clientInfo": {"name": "arena-contract-state", "version": "1.0"}})
    if not session:
        raise RuntimeError("MCP session missing")
    def tool(name, arguments, request_id):
        result, _ = call("tools/call", {"name": name, "arguments": arguments}, session, request_id)
        return text(result)
    chain = tool("get_chain_info", {}, 2)
    if chain["chainId"] != 1672 or not chain["chainIdMatches"]:
        raise RuntimeError("Unexpected chain")
    block = chain["latestBlockHex"]
    calls = {name: tool("eth_call", {"transaction": {"to": CONTRACT, "data": selector}, "block": block}, i)["result"]
             for i, (name, selector) in enumerate(SELECTORS.items(), 3)}
    decimals = int(calls["decimals"], 16)
    if not 0 <= decimals <= 36:
        raise ValueError("Unexpected token decimals")
    raw = int(calls["totalSupply"], 16)
    whole, fraction = divmod(raw, 10 ** decimals)
    supply = str(whole) + (("." + str(fraction).zfill(decimals).rstrip("0")) if fraction else "")
    return {"network": "Pharos mainnet", "chain_id": chain["chainId"], "contract": CONTRACT,
            "block": int(block, 16), "name": decode_string(calls["name"]),
            "symbol": decode_string(calls["symbol"]), "decimals": decimals,
            "total_supply_raw": str(raw), "total_supply": supply}


def self_test():
    def abi(value):
        data = value.encode()
        return "0x" + (32).to_bytes(32, "big").hex() + len(data).to_bytes(32, "big").hex() + data.hex().ljust(64, "0")
    fake = {"name": abi("USD Coin"), "symbol": abi("USDC"),
            "decimals": hex(6), "totalSupply": hex(123450000)}
    def call(method, params, session=None, request_id=1):
        if method == "initialize":
            return {}, "test-session"
        name = params["name"]
        value = ({"chainId": 1672, "chainIdMatches": True, "latestBlockHex": "0xa"} if name == "get_chain_info"
                 else {"result": fake[next(k for k, v in SELECTORS.items() if v == params["arguments"]["transaction"]["data"])]})
        if name == "eth_call":
            assert params["arguments"]["block"] == "0xa"
        return {"content": [{"type": "text", "text": json.dumps(value)}]}, None
    output = snapshot(call)
    assert output["total_supply"] == "123.45" and output["block"] == 10
    assert output["name"] == "USD Coin" and output["symbol"] == "USDC"


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        self_test()
        print("self-test passed")
    else:
        print(json.dumps(snapshot(), indent=2))

"""Dependency-free self-test for threshold_guardian.py."""
import json

import threshold_guardian as guardian


def fake_exchange(method, params, session=None, request_id=1):
    if method == "initialize":
        return {}, "test-session"
    name = params["name"]
    values = {
        "get_chain_info": {
            "chainId": 1672,
            "chainIdMatches": True,
            "latestBlockHex": "0x64",
        },
        "get_gas_price": {"gasPriceGwei": "10"},
        "eth_call": {"result": hex(50_000_000 * 10**6)},
    }
    if name == "eth_call":
        assert params["arguments"]["block"] == "0x64"
    return {"content": [{"type": "text", "text": json.dumps(values[name])}]}, None


def main():
    snapshot = guardian.read_chain(fake_exchange)
    assert snapshot == {
        "block_number": 100,
        "gas_price_gwei": "10",
        "usdc_total_supply": "50000000",
    }
    fire = guardian.evaluate(snapshot, [
        {"metric": "block_number", "operator": ">=", "threshold": "99"},
        {"metric": "gas_price_gwei", "operator": "<=", "threshold": "10"},
        {"metric": "usdc_total_supply", "operator": ">", "threshold": "49999999"},
    ])
    assert fire["decision"] == "FIRE"
    assert all(item["passed"] for item in fire["conditions"])
    hold = guardian.evaluate(snapshot, [
        {"metric": "block_number", "operator": ">=", "threshold": "101"},
        {"metric": "gas_price_gwei", "operator": "<=", "threshold": "9"},
        {"metric": "usdc_total_supply", "operator": ">", "threshold": "50000000"},
    ])
    assert hold["decision"] == "HOLD"
    assert not any(item["passed"] for item in hold["conditions"])
    try:
        guardian.evaluate(snapshot, [
            {"metric": "unknown", "operator": ">", "threshold": "0"},
            {"metric": "block_number", "operator": ">", "threshold": "0"},
            {"metric": "gas_price_gwei", "operator": ">", "threshold": "0"},
        ])
    except ValueError as error:
        assert "Unknown metric" in str(error)
    else:
        raise AssertionError("unknown metric accepted")
    print("self-test passed")


if __name__ == "__main__":
    main()

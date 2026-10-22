# Docs MCP Onboarding — Pharos Agent Arena

This is a first-use log from building two read-only Pharos developer tools with Developer Docs MCP and Chain MCP on 22 October 2026.

## Goal

Build a sourced docs CLI, then use the documented Chain MCP interface to run a restart-safe USDC event monitor on Pharos mainnet.

## Step-by-step log

### 1. Find the Chain MCP endpoint and tools

**Exact query**

```text
What is the exact Pharos Chain MCP endpoint and what tools does it expose?
```

**Docs MCP answer**

It returned `https://mcp.pharos.xyz/mcp`, no authentication, 14 tools, a 120 requests-per-minute limit, and links to the MCP page.

**Result**

This was enough to identify `get_chain_info`, `get_block_number`, and `get_logs` for a read-only monitor.

### 2. Find the event-log filter

**Exact query**

```text
What are the exact get_logs parameters for Pharos Chain MCP, including block range and topics?
```

**Docs MCP answer**

It showed `fromBlock`, `toBlock`, `address`, and `topics`, plus a 1,000-block maximum per Chain MCP call.

**Result**

The monitor now filters one USDC contract and the ERC-20 `Transfer` topic, and pages ranges at 1,000 blocks or fewer.

### 3. Check the underlying RPC range limit

**Exact query**

```text
What is the maximum supported eth_getLogs block range on Pharos Pacific Mainnet?
```

**Docs MCP answer**

It returned 100 blocks when rate limiting is enabled and a 10,000-block fallback cap.

**Breakdown 1 — conflicting limits without context**

The 1,000-block Chain MCP limit and 100/10,000-block RPC limits can all be true at different layers, but the answers do not explain which limit applies when a developer calls Chain MCP.

**Suggested fix**

The MCP page should say: “For the hosted Chain MCP `get_logs` tool, use at most 1,000 blocks per call. Direct JSON-RPC providers may enforce different limits; check that provider separately. The Chain MCP limit takes precedence when using `https://mcp.pharos.xyz/mcp`."

### 4. Check exact schema and multi-address behavior

**Exact query**

```text
Does Pharos Chain MCP get_logs accept an array of contract addresses? Show the exact schema.
```

**Docs MCP answer**

It said the docs do not confirm array support and do not publish the exact MCP JSON Schema. The only documented example uses one address string.

**Breakdown 2 — schema is missing**

A client cannot safely validate inputs or know whether standard Ethereum multi-address filters are preserved by the MCP wrapper.

**Suggested fix**

Publish the exact tool input schema, including required fields, accepted block tags, whether `address` is `string` or `string[]`, topic OR-array semantics, response shape, and representative validation errors.

### 5. Implement the MCP transport

**Exact query**

```text
What HTTP headers and initialization handshake are required before calling Pharos Chain MCP tools from Python?
```

**Docs MCP answer**

```text
No good answer found in Pharos docs. Try a more specific question.
```

**Breakdown 3 — no end-to-end client handshake**

The endpoint alone is insufficient for a raw HTTP client. A working client must know how to call `initialize`, request both JSON and event-stream responses, retain `Mcp-Session-Id`, and pass it to later `tools/call` requests.

**Suggested fix**

Add a complete Python standard-library example showing:

1. `POST /mcp` with JSON-RPC `initialize`.
2. `Accept: application/json, text/event-stream` and `Content-Type: application/json`.
3. Reading `Mcp-Session-Id` from the response.
4. Sending that session ID with `tools/call`.
5. Parsing plain JSON and SSE `data:` responses.
6. Handling session expiration and MCP errors.

## What worked by the end

- Built `pharos_docs.py`, a natural-language Docs MCP CLI with source links and explicit no-answer handling.
- Built `arena_event_monitor.py`, a restart-safe Chain MCP monitor for USDC `Transfer` events.
- Self-tests passed for both tools.
- A fresh mainnet run decoded 77 events in one poll and 89 new events in the next poll.
- The two polls shared zero `(transaction hash, log index)` keys.
- No wallet, signature, or transaction was used.

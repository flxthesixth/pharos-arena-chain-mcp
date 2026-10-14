"""Ask the Pharos Developer Docs MCP from a terminal (read-only)."""
import argparse
import json
import re
from urllib.request import Request, urlopen

MCP = "https://docs.pharos.xyz/~gitbook/mcp"
NO_ANSWER = re.compile(r"\b(?:cannot|can't|could not|unable to|no (?:good |relevant )?(?:information|answer|documentation)|not (?:found|documented))\b", re.I)


def ask(question):
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": "askQuestion", "arguments": {"question": question}}}
    request = Request(MCP, json.dumps(payload).encode(), {
        "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}, method="POST")
    with urlopen(request, timeout=60) as response:
        body = response.read().decode()
    if body.startswith("event:"):
        body = next(line[6:] for line in body.splitlines() if line.startswith("data: "))
    data = json.loads(body)
    if "error" in data:
        raise RuntimeError(data["error"])
    result = data["result"]
    if result.get("isError"):
        raise RuntimeError(result["content"])
    return "\n".join(part["text"] for part in result["content"] if part.get("type") == "text")


def format_answer(raw):
    answer, _, sources = raw.partition("# Sources")
    answer = answer.strip()
    if not answer or NO_ANSWER.search(answer):
        return "No good answer found in Pharos docs. Try a more specific question."
    links = list(dict.fromkeys(re.findall(r"https://docs\.pharos\.xyz/[\w./-]+", sources)))
    if not links:
        return "No sourced answer found in Pharos docs. Try a more specific question."
    # ponytail: show only top three MCP citations; add page-level verification if ranking proves unreliable.
    return answer + "\n\nSources:\n" + "\n".join("- " + url for url in links[:3])


def self_test():
    assert format_answer("Pharos uses chain ID 1672.\n# Sources\n- https://docs.pharos.xyz/getting-started/network/pacific-mainnet") == (
        "Pharos uses chain ID 1672.\n\nSources:\n- https://docs.pharos.xyz/getting-started/network/pacific-mainnet")
    assert format_answer("I cannot find information about dragons.\n# Sources\n- https://docs.pharos.xyz/introduction/readme").startswith("No good answer")
    assert format_answer("Unsourced answer").startswith("No sourced answer")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", nargs="*", help="Natural-language Pharos docs question")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("self-test passed")
        return
    if not args.question:
        parser.error("provide a natural-language question")
    try:
        print(format_answer(ask(" ".join(args.question))))
    except (OSError, ValueError, KeyError, StopIteration, RuntimeError) as exc:
        parser.exit(1, f"Docs MCP request failed: {exc}\n")


if __name__ == "__main__":
    main()

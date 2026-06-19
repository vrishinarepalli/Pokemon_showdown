"""Connectivity smoke test for the Groq client.

Validates: API key works, the model is reachable, latency is acceptable, and the
model returns sane Pokemon answers. Run:  python -m bot.llm.smoke_test
"""

import time

from bot.llm.client import GroqClient


def main() -> None:
    client = GroqClient()
    print(f"model = {client.model}")

    checks = [
        ("Is Charizard (Fire/Flying) weak to Rock-type moves? Answer yes or no only.", "yes"),
        ("Does Earthquake (Ground) hit a Flying-type for damage? Answer yes or no only.", "no"),
    ]
    for question, expected in checks:
        t = time.time()
        reply = client.ask(
            "You are a precise Pokemon battle assistant. Answer with a single word.",
            question,
            max_tokens=8,
        )
        dt = time.time() - t
        ok = expected in reply.lower()
        print(f"  [{'OK ' if ok else 'BAD'}] ({dt:4.2f}s) {reply!r}  (expected ~{expected!r})")

    print(f"\n{client.n_calls} calls, avg latency {client.total_latency / max(client.n_calls,1):.2f}s")


if __name__ == "__main__":
    main()

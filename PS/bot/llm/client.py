"""Groq LLM client for the M5 agent.

Reads GROQ_API_KEY (and optional GROQ_MODEL) from the environment, falling back
to a local .env file at the repo root. The key is never hard-coded.

Groq is OpenAI-compatible and fast — a good fit for online play where each turn
has a timer. The client is intentionally thin: build messages/tools elsewhere,
call chat(), interpret the response there.
"""

import os
import time
from pathlib import Path

_ENV_LOADED = False

# Sensible free Groq default. Override with GROQ_MODEL or the model= arg.
#   llama-3.3-70b-versatile : strong reasoning + reliable tool use
#   llama-3.1-8b-instant    : fastest, for the latency-critical fast path
DEFAULT_MODEL = "llama-3.3-70b-versatile"


def _load_dotenv() -> None:
    """Populate os.environ from the repo-root .env (once). Does not override
    values already present in the real environment."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    root = Path(__file__).resolve().parents[2]  # bot/llm/client.py -> PS/
    env_path = root / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())
    _ENV_LOADED = True


class GroqClient:
    def __init__(self, model: str | None = None, timeout: float = 30.0):
        _load_dotenv()
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to the environment or the repo-root .env."
            )
        from groq import Groq

        self._client = Groq(api_key=api_key, timeout=timeout)
        self.model = model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
        # Lightweight call accounting (helps us watch free-tier usage).
        self.n_calls = 0
        self.total_latency = 0.0
        self.total_tokens = 0

    def chat(self, messages, tools=None, temperature: float = 0.2, max_tokens: int = 1024):
        """Raw chat completion. Returns the Groq response object."""
        kwargs = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        start = time.time()
        resp = self._client.chat.completions.create(**kwargs)
        self.n_calls += 1
        self.total_latency += time.time() - start
        usage = getattr(resp, "usage", None)
        self.total_tokens += getattr(usage, "total_tokens", 0) or 0
        return resp

    def ask(self, system: str, user: str, **kw) -> str:
        """Convenience: single-turn text completion, returns the content string."""
        resp = self.chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kw,
        )
        return (resp.choices[0].message.content or "").strip()

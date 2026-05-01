"""LLM router: Ollama (local) or Anthropic (cloud), with latency logging."""
from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from pce.config import settings

log = structlog.get_logger()

SYSTEM_PROMPT = (
    "You are a personal context assistant. Answer the user's question using ONLY "
    "the provided context snippets. If the context is insufficient, say so clearly. "
    "Always reference which [Source N] you used in your answer."
)


@dataclass
class LLMResponse:
    answer: str
    backend: str
    latency_ms: int
    input_tokens: int
    output_tokens: int


def _build_user_message(question: str, sources: list[dict]) -> str:
    context_blocks = []
    for i, s in enumerate(sources, start=1):
        label = s.get("title") or s.get("path") or s.get("url") or "unknown"
        source_type = s.get("source", "")
        chunks = "\n".join(s.get("chunks", [s.get("snippet", "")]))
        context_blocks.append(f"[Source {i}] {label} ({source_type})\n{chunks}")

    context = "\n\n---\n\n".join(context_blocks)
    return f"Context:\n\n{context}\n\nQuestion: {question}"


async def _call_ollama(messages: list[dict]) -> LLMResponse:
    import httpx

    t0 = time.monotonic()
    payload = {
        "model": settings.ollama_model,
        "messages": messages,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{settings.ollama_base_url}/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

    answer = data["message"]["content"]
    latency_ms = int((time.monotonic() - t0) * 1000)
    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)

    log.info("llm_ollama", latency_ms=latency_ms, in_tok=prompt_tokens, out_tok=completion_tokens)
    return LLMResponse(
        answer=answer,
        backend="ollama",
        latency_ms=latency_ms,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
    )


async def _call_anthropic(messages: list[dict]) -> LLMResponse:
    import anthropic

    t0 = time.monotonic()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    answer = response.content[0].text
    latency_ms = int((time.monotonic() - t0) * 1000)
    in_tok = response.usage.input_tokens
    out_tok = response.usage.output_tokens

    log.info("llm_anthropic", latency_ms=latency_ms, in_tok=in_tok, out_tok=out_tok)
    return LLMResponse(
        answer=answer,
        backend="anthropic",
        latency_ms=latency_ms,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )


async def ask(question: str, sources: list[dict]) -> LLMResponse:
    """Route a question + retrieved sources to the configured LLM backend."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_message(question, sources)},
    ]

    if settings.llm_backend == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("PCE_ANTHROPIC_API_KEY is not set")
        # Pass system prompt via Anthropic's system param, not in messages
        messages = [m for m in messages if m["role"] != "system"]
        return await _call_anthropic(messages)

    return await _call_ollama(messages)

import hashlib
import json
import time
from typing import Dict, List, Optional

import litellm
from litellm.caching.caching import Cache
from fastapi import HTTPException

# Suppress noisy LiteLLM logs
import logging
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("LiteLLM Router").setLevel(logging.WARNING)

# Enable LiteLLM built-in in-memory cache (type="local" = in-memory, works without Redis/disk)
litellm.cache = Cache(type="local")
litellm.set_verbose = False


class LLMManager:
    MODEL = "gemini/gemini-flash-lite-latest"

    def __init__(self, keys: List[Dict]):
        """
        keys: [{"id": "key_1", "value": "AIzaSy..."}, ...]
        """
        self.keys = keys
        self.cache_enabled = True
        # Reliable in-memory cache dict (SHA-256 of model+messages → result)
        self._mem_cache: Dict[str, Dict] = {}

    def _make_cache_key(self, messages: List[Dict]) -> str:
        payload = json.dumps(
            {"model": self.MODEL, "messages": messages}, sort_keys=True
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    async def chat(
        self,
        messages: List[Dict],
        simulated_failures: Optional[Dict] = None,
    ) -> Dict:
        simulated_failures = simulated_failures or {}

        # ── 1. Check in-memory cache ─────────────────────────────────────────
        cache_key = self._make_cache_key(messages)
        if self.cache_enabled and cache_key in self._mem_cache:
            cached = self._mem_cache[cache_key]
            start = time.perf_counter()
            latency_ms = int((time.perf_counter() - start) * 1000)
            return {
                "reply": cached["reply"],
                "resolution_source": "LLM_CACHE",
                "model": cached["model"],
                "latency_ms": latency_ms,
                "input_tokens": cached["input_tokens"],
                "output_tokens": cached["output_tokens"],
                "key_id": None,
                "fallback_attempts": 0,
            }

        # ── 2. Try each key with auto-failover ───────────────────────────────
        fallback_attempts = 0
        last_error: str = "no keys configured"

        for key_info in self.keys:
            key_id = key_info["id"]
            key_value = key_info["value"]

            # Honour simulated failure for this key or wildcard
            sim_status = simulated_failures.get(key_id) or simulated_failures.get("*")
            if sim_status is not None:
                fallback_attempts += 1
                last_error = f"simulated {sim_status} on {key_id}"
                continue

            try:
                start = time.perf_counter()
                response = await litellm.acompletion(
                    model=self.MODEL,
                    messages=messages,
                    api_key=key_value,
                    caching=True,
                    num_retries=0,
                    timeout=60,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)

                # Detect LiteLLM cache hit
                hidden = getattr(response, "_hidden_params", {}) or {}
                is_cache_hit = bool(hidden.get("cache_hit", False))

                reply: str = response.choices[0].message.content or ""
                usage = response.usage or {}
                input_tokens: int = getattr(usage, "prompt_tokens", 0) or 0
                output_tokens: int = getattr(usage, "completion_tokens", 0) or 0
                model_used: str = response.model or self.MODEL

                result = {
                    "reply": reply,
                    "resolution_source": "LLM_CACHE" if is_cache_hit else "LIVE_INFERENCE",
                    "model": model_used,
                    "latency_ms": latency_ms,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "key_id": None if is_cache_hit else key_id,
                    "fallback_attempts": 0 if is_cache_hit else fallback_attempts,
                }

                # Also store in our own in-memory cache for guaranteed hits
                if self.cache_enabled and not is_cache_hit:
                    self._mem_cache[cache_key] = {
                        "reply": reply,
                        "model": model_used,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                    }

                return result

            except Exception as exc:
                err = str(exc)
                # Treat rate-limit / server errors as retriable
                retriable = any(
                    code in err
                    for code in ["429", "500", "502", "503", "quota", "rate_limit", "RateLimitError"]
                )
                if retriable:
                    fallback_attempts += 1
                    last_error = err
                    continue
                # Non-retriable — surface immediately
                raise HTTPException(status_code=502, detail=f"LLM error: {err[:300]}")

        # All keys exhausted
        raise HTTPException(status_code=503, detail="all providers unavailable")

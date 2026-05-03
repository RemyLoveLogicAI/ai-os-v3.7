"""
AI OS v3.7 — LLM Router
Intelligent multi-backend routing with Ollama-first, full fallback chain.
Providers: Ollama → OpenAI → Anthropic
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

log = logging.getLogger("ai-os.llm-router")


@dataclass
class RouterConfig:
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))
    timeout_seconds: float = 30.0
    max_retries: int = 2


class LLMRouter:
    """
    Routes LLM requests across Ollama → OpenAI → Anthropic with automatic fallback.
    Ollama is always tried first (free, local). Cloud providers are fallback only.
    """

    def __init__(self, config: RouterConfig = None):
        self.config = config or RouterConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._provider_health: dict[str, bool] = {
            "ollama": True,
            "openai": True,
            "anthropic": True,
        }

    async def initialize(self):
        self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
        log.info(f"[ROUTER] Initialized. Ollama: {self.config.ollama_base_url}")

    async def shutdown(self):
        if self._client:
            await self._client.aclose()

    async def route(
        self,
        prompt: str,
        system: Optional[str] = None,
        model_preference: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> dict:
        """Route prompt through best available backend with fallback chain."""

        providers = self._build_provider_chain(model_preference)
        last_error = None

        for provider_fn, provider_name in providers:
            if not self._provider_health.get(provider_name, True):
                log.debug(f"[ROUTER] Skipping {provider_name} (marked unhealthy)")
                continue
            try:
                log.info(f"[ROUTER] Trying provider: {provider_name}")
                result = await provider_fn(prompt, system, max_tokens, temperature)
                result["provider"] = provider_name
                result["fallback"] = provider_name != providers[0][1]
                self._provider_health[provider_name] = True
                return result
            except Exception as e:
                log.warning(f"[ROUTER] {provider_name} failed: {e}")
                last_error = e
                self._provider_health[provider_name] = False
                continue

        raise RuntimeError(f"All LLM backends failed. Last error: {last_error}")

    async def complete_direct(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> dict:
        """Direct completion bypassing routing logic."""
        if "gpt" in model.lower():
            return await self._openai(prompt, system, max_tokens, temperature)
        elif "claude" in model.lower():
            return await self._anthropic(prompt, system, max_tokens, temperature)
        else:
            return await self._ollama(prompt, system, max_tokens, temperature, model=model)

    def _build_provider_chain(self, model_preference: Optional[str]) -> list:
        """Build ordered list of (provider_fn, name) tuples."""
        chain = []

        # Honor explicit preference
        if model_preference:
            mp = model_preference.lower()
            if "gpt" in mp or "openai" in mp:
                if self.config.openai_api_key:
                    chain.append((self._openai, "openai"))
            elif "claude" in mp or "anthropic" in mp:
                if self.config.anthropic_api_key:
                    chain.append((self._anthropic, "anthropic"))
            else:
                chain.append((self._ollama, "ollama"))

        # Default: Ollama first, then cloud fallbacks
        if not chain:
            chain.append((self._ollama, "ollama"))
            if self.config.openai_api_key:
                chain.append((self._openai, "openai"))
            if self.config.anthropic_api_key:
                chain.append((self._anthropic, "anthropic"))

        return chain

    async def _ollama(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: int,
        temperature: float,
        model: Optional[str] = None,
    ) -> dict:
        """Call Ollama local inference API."""
        url = f"{self.config.ollama_base_url}/api/generate"
        payload = {
            "model": model or self.config.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        return {
            "content": data.get("response", ""),
            "model": data.get("model", self.config.ollama_model),
            "tokens": data.get("eval_count"),
        }

    async def _openai(
        self, prompt: str, system: Optional[str], max_tokens: int, temperature: float
    ) -> dict:
        """Call OpenAI Chat Completions API."""
        if not self.config.openai_api_key:
            raise ValueError("OpenAI API key not configured")

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await self._client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
            json={
                "model": self.config.openai_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "model": data["model"],
            "tokens": data["usage"]["total_tokens"],
        }

    async def _anthropic(
        self, prompt: str, system: Optional[str], max_tokens: int, temperature: float
    ) -> dict:
        """Call Anthropic Messages API."""
        if not self.config.anthropic_api_key:
            raise ValueError("Anthropic API key not configured")

        body = {
            "model": self.config.anthropic_model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        resp = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.config.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

        return {
            "content": data["content"][0]["text"],
            "model": data["model"],
            "tokens": data["usage"]["input_tokens"] + data["usage"]["output_tokens"],
        }

    def configured_providers(self) -> list[str]:
        providers = ["ollama"]
        if self.config.openai_api_key:
            providers.append("openai")
        if self.config.anthropic_api_key:
            providers.append("anthropic")
        return providers

    async def health_check(self) -> dict:
        results = {}
        try:
            resp = await self._client.get(
                f"{self.config.ollama_base_url}/api/tags", timeout=5.0
            )
            results["ollama"] = "healthy" if resp.status_code == 200 else "degraded"
        except Exception:
            results["ollama"] = "unreachable"

        results["openai"] = "configured" if self.config.openai_api_key else "not_configured"
        results["anthropic"] = "configured" if self.config.anthropic_api_key else "not_configured"
        return results

    async def status(self) -> dict:
        health = await self.health_check()
        return {
            "providers": self.configured_providers(),
            "health": health,
            "provider_health_cache": self._provider_health,
        }

    async def reload_config(self):
        self.config = RouterConfig()
        self._provider_health = {k: True for k in self._provider_health}
        log.info("[ROUTER] Config reloaded from environment")

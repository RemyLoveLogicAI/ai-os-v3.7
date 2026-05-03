"""
AI OS v3.7 — LLM Router
Intelligent multi-backend routing with named Ollama fleet + cloud fallback chain.

Ollama Fleet (local, zero cost):
  agent   → hermes3:70b     — complex tasks, multi-step reasoning, orchestration
  reason  → deepseek-r1:32b — chain-of-thought, analysis, math, logic
  code    → qwen2.5:32b     — coding, debugging, technical generation
  default → qwen2.5:14b     — balanced daily driver, general purpose
  fast    → gemma3:4b       — snappy responses, classification, simple Q&A

Cloud Fallback Chain: Ollama → OpenAI → Anthropic
"""

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx

log = logging.getLogger("ai-os.llm-router")


# ── Fleet Definition ─────────────────────────────────────────────────────────

OLLAMA_FLEET: dict[str, str] = {
    "agent":   "hermes3:70b",       # Complex tasks, orchestration, multi-step
    "reason":  "deepseek-r1:32b",   # Chain-of-thought, logic, analysis, math
    "code":    "qwen2.5:32b",       # Coding, debugging, technical generation
    "default": "qwen2.5:14b",       # Balanced, general purpose daily driver
    "fast":    "gemma3:4b",         # Speed, classification, simple Q&A
}

# Intent → fleet target auto-mapping
INTENT_MAP: dict[str, str] = {
    # Agent / orchestration
    "agent": "agent", "orchestrate": "agent", "plan": "agent",
    "multi-step": "agent", "workflow": "agent", "dispatch": "agent",
    # Reasoning
    "reason": "reason", "analyze": "reason", "math": "reason",
    "logic": "reason", "debug": "reason", "explain": "reason",
    "think": "reason", "chain": "reason",
    # Code
    "code": "code", "coding": "code", "generate": "code",
    "refactor": "code", "fix": "code", "review": "code",
    "script": "code", "function": "code",
    # Fast
    "fast": "fast", "quick": "fast", "classify": "fast",
    "simple": "fast", "short": "fast", "yes/no": "fast",
    # Default
    "default": "default", "general": "default", "chat": "default",
}


# ── Config ───────────────────────────────────────────────────────────────────

@dataclass
class RouterConfig:
    # Ollama
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_default_target: str = field(
        default_factory=lambda: os.getenv("OLLAMA_DEFAULT_TARGET", "default")
    )
    # Custom fleet overrides via env (e.g. OLLAMA_MODEL_AGENT=llama3)
    ollama_fleet: dict[str, str] = field(default_factory=lambda: {
        k: os.getenv(f"OLLAMA_MODEL_{k.upper()}", v)
        for k, v in OLLAMA_FLEET.items()
    })
    # Cloud fallbacks
    openai_api_key:    str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model:      str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model:   str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"))
    # Behaviour
    timeout_seconds: float = 60.0   # 70b models need more time
    max_retries:     int   = 2


# ── Router ───────────────────────────────────────────────────────────────────

class LLMRouter:
    """
    Routes LLM requests across the local Ollama fleet and cloud fallbacks.

    Routing priority:
      1. Explicit model_preference string  → direct
      2. intent kwarg                      → fleet target via INTENT_MAP
      3. fleet_target kwarg                → named fleet target
      4. Default fleet target (qwen2.5:14b)
      5. Cloud fallbacks if Ollama unreachable
    """

    def __init__(self, config: RouterConfig = None):
        self.config = config or RouterConfig()
        self._client: Optional[httpx.AsyncClient] = None
        self._provider_health: dict[str, bool] = {
            "ollama": True, "openai": True, "anthropic": True
        }
        self._fleet_health: dict[str, bool] = {k: True for k in OLLAMA_FLEET}
        self._request_count: int = 0
        self._start_time: float = time.time()

    async def initialize(self):
        self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)
        log.info(f"[ROUTER] Initialized | Ollama: {self.config.ollama_base_url}")
        log.info(f"[ROUTER] Fleet: {list(self.config.ollama_fleet.keys())}")

    async def shutdown(self):
        if self._client:
            await self._client.aclose()

    # ── Primary route entry point ─────────────────────────────────────────

    async def route(
        self,
        prompt: str,
        system: Optional[str] = None,
        model_preference: Optional[str] = None,
        fleet_target: Optional[str] = None,
        intent: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> dict:
        """
        Route a prompt to the best available backend.

        Selection order:
          model_preference → exact model string (e.g. 'hermes3:70b')
          intent           → auto-mapped fleet target (e.g. 'code' → qwen2.5:32b)
          fleet_target     → named target (e.g. 'agent', 'fast', 'reason')
          default          → qwen2.5:14b
          fallback         → OpenAI → Anthropic if Ollama down
        """
        self._request_count += 1

        # Resolve which Ollama model to use
        resolved_model, resolved_target = self._resolve_model(
            model_preference, fleet_target, intent
        )

        # Try Ollama fleet first
        if self._provider_health["ollama"]:
            try:
                result = await self._ollama(
                    prompt, system, max_tokens, temperature, model=resolved_model
                )
                result["provider"]      = "ollama"
                result["fleet_target"]  = resolved_target
                result["fallback"]      = False
                self._provider_health["ollama"] = True
                return result
            except Exception as e:
                log.warning(f"[ROUTER] Ollama/{resolved_target} failed: {e}")
                self._provider_health["ollama"] = False

        # Cloud fallback chain
        for provider_fn, name in self._cloud_chain():
            try:
                log.info(f"[ROUTER] Falling back to {name}")
                result = await provider_fn(prompt, system, max_tokens, temperature)
                result["provider"]     = name
                result["fleet_target"] = None
                result["fallback"]     = True
                self._provider_health[name] = True
                return result
            except Exception as e:
                log.warning(f"[ROUTER] {name} failed: {e}")
                self._provider_health[name] = False

        raise RuntimeError("All LLM backends failed — Ollama down, no cloud keys configured.")

    # ── Direct completion (bypass routing) ───────────────────────────────

    async def complete_direct(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> dict:
        """Direct completion to a specific model string."""
        if "gpt" in model.lower() or "openai" in model.lower():
            return await self._openai(prompt, system, max_tokens, temperature)
        elif "claude" in model.lower() or "anthropic" in model.lower():
            return await self._anthropic(prompt, system, max_tokens, temperature)
        else:
            # Treat as Ollama model name
            return await self._ollama(prompt, system, max_tokens, temperature, model=model)

    # ── Model resolution ─────────────────────────────────────────────────

    def _resolve_model(
        self,
        model_preference: Optional[str],
        fleet_target: Optional[str],
        intent: Optional[str],
    ) -> tuple[str, str]:
        """Return (model_string, fleet_target_name)."""

        # 1. Explicit model string (could be anything Ollama has)
        if model_preference:
            # Check if it's a fleet alias
            if model_preference in self.config.ollama_fleet:
                target = model_preference
                return self.config.ollama_fleet[target], target
            # Treat as raw model name
            return model_preference, "custom"

        # 2. Intent → fleet target
        if intent:
            target = INTENT_MAP.get(intent.lower(), self.config.ollama_default_target)
            model  = self.config.ollama_fleet.get(target, self.config.ollama_fleet["default"])
            return model, target

        # 3. Explicit fleet target
        if fleet_target:
            if fleet_target not in self.config.ollama_fleet:
                log.warning(f"[ROUTER] Unknown fleet_target '{fleet_target}', using default")
                fleet_target = "default"
            return self.config.ollama_fleet[fleet_target], fleet_target

        # 4. Default
        target = self.config.ollama_default_target
        return self.config.ollama_fleet.get(target, self.config.ollama_fleet["default"]), target

    def _cloud_chain(self):
        chain = []
        if self.config.openai_api_key:
            chain.append((self._openai, "openai"))
        if self.config.anthropic_api_key:
            chain.append((self._anthropic, "anthropic"))
        return chain

    # ── Ollama ────────────────────────────────────────────────────────────

    async def _ollama(
        self,
        prompt: str,
        system: Optional[str],
        max_tokens: int,
        temperature: float,
        model: Optional[str] = None,
    ) -> dict:
        url     = f"{self.config.ollama_base_url}/api/generate"
        payload = {
            "model":   model or self.config.ollama_fleet["default"],
            "prompt":  prompt,
            "stream":  False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if system:
            payload["system"] = system

        resp = await self._client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()

        return {
            "content": data.get("response", ""),
            "model":   data.get("model", model),
            "tokens":  data.get("eval_count"),
        }

    # ── OpenAI ────────────────────────────────────────────────────────────

    async def _openai(
        self, prompt: str, system: Optional[str], max_tokens: int, temperature: float
    ) -> dict:
        if not self.config.openai_api_key:
            raise ValueError("OpenAI API key not configured")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await self._client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
            json={"model": self.config.openai_model, "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature},
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "content": data["choices"][0]["message"]["content"],
            "model":   data["model"],
            "tokens":  data["usage"]["total_tokens"],
        }

    # ── Anthropic ─────────────────────────────────────────────────────────

    async def _anthropic(
        self, prompt: str, system: Optional[str], max_tokens: int, temperature: float
    ) -> dict:
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
            "model":   data["model"],
            "tokens":  data["usage"]["input_tokens"] + data["usage"]["output_tokens"],
        }

    # ── Introspection ─────────────────────────────────────────────────────

    def configured_providers(self) -> list[str]:
        providers = ["ollama"]
        if self.config.openai_api_key:    providers.append("openai")
        if self.config.anthropic_api_key: providers.append("anthropic")
        return providers

    def fleet_info(self) -> dict:
        """Return the full routing table."""
        return {
            "targets": {
                name: {
                    "model":       model,
                    "description": _FLEET_DESCRIPTIONS.get(name, ""),
                    "healthy":     self._fleet_health.get(name, True),
                }
                for name, model in self.config.ollama_fleet.items()
            },
            "default_target":  self.config.ollama_default_target,
            "intent_map_keys": list(INTENT_MAP.keys()),
        }

    async def health_check(self) -> dict:
        results = {}
        try:
            resp = await self._client.get(
                f"{self.config.ollama_base_url}/api/tags", timeout=5.0
            )
            if resp.status_code == 200:
                pulled_models = [m["name"] for m in resp.json().get("models", [])]
                results["ollama"] = "healthy"
                results["ollama_models_available"] = pulled_models
                # Check which fleet targets are actually pulled
                for target, model in self.config.ollama_fleet.items():
                    base = model.split(":")[0]
                    available = any(base in m for m in pulled_models)
                    results[f"fleet_{target}"] = "ready" if available else "not_pulled"
                    self._fleet_health[target] = available
            else:
                results["ollama"] = "degraded"
        except Exception:
            results["ollama"] = "unreachable"

        results["openai"]     = "configured" if self.config.openai_api_key    else "not_configured"
        results["anthropic"]  = "configured" if self.config.anthropic_api_key else "not_configured"
        return results

    async def status(self) -> dict:
        health = await self.health_check()
        uptime = time.time() - self._start_time
        return {
            "providers":      self.configured_providers(),
            "fleet":          self.fleet_info(),
            "health":         health,
            "request_count":  self._request_count,
            "uptime_seconds": round(uptime, 1),
        }

    async def reload_config(self):
        self.config = RouterConfig()
        self._provider_health = {k: True for k in self._provider_health}
        self._fleet_health    = {k: True for k in self._fleet_health}
        log.info("[ROUTER] Config reloaded from environment")


# ── Fleet Descriptions ────────────────────────────────────────────────────────

_FLEET_DESCRIPTIONS = {
    "agent":   "Complex tasks, multi-step orchestration, autonomous workflows (hermes3:70b)",
    "reason":  "Chain-of-thought, analysis, math, logic, deep thinking (deepseek-r1:32b)",
    "code":    "Code generation, debugging, refactoring, technical writing (qwen2.5:32b)",
    "default": "Balanced general-purpose daily driver (qwen2.5:14b)",
    "fast":    "Speed-optimized for classification, simple Q&A, routing (gemma3:4b)",
}

# AI OS v3.7

> **LoveLogicAI LLC** — Built by Jeremy "Remy" Morgan-Jones Sr.  
> *Adversity is the forge. Protocol is the edge.*

Production-grade AI Operating System with intelligent LLM routing, hot-swappable skill marketplace, and full Ollama/OpenAI/Anthropic fallback chain.

---

## What's Inside

```
ai-os-v3.7/
├── src/
│   ├── api/server.py          — FastAPI: /route /skills /health /complete
│   ├── core/llm_router.py     — Ollama-first LLM router with fallback chain
│   └── marketplace/registry.py — Hot-swap skill marketplace + circuit breaker
├── protocols/
│   ├── soul.md                — 16-phase canonical execution protocol
│   ├── zo-hardening-dispatch.md
│   ├── nats-rehydration-protocol.md
│   └── orion-hub-architecture.md
├── scripts/
│   └── zo-triage-and-harden.sh — Smart env discovery + auto-hardening
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── deploy/
│   ├── railway.toml           — Railway.app deploy config
│   └── render.yaml            — Render.com blueprint
├── .github/workflows/ci.yml   — 6-job CI/CD pipeline
└── tests/test_api.py          — Async API test suite
```

## Quick Start

```bash
# 1. Clone
git clone https://github.com/Remylovelogicai/ai-os-v3.7.git
cd ai-os-v3.7

# 2. Configure
cp .env.example .env
# Edit .env — add at least one LLM provider

# 3. Run with Docker
docker compose -f docker/docker-compose.yml up -d

# 4. Verify
curl http://localhost:8000/health
```

## Deploy

```bash
# Railway (fastest)
npm install -g @railway/cli && railway login
railway init && railway up

# Render
# Connect repo at render.com → New → Blueprint → select this repo
```

## API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | System + component health |
| POST | `/v1/route` | Route prompt through best LLM |
| POST | `/v1/complete` | Direct completion to specific model |
| GET | `/v1/skills` | List marketplace skills |
| POST | `/v1/skills/{name}/invoke` | Invoke a skill |
| GET | `/v1/router/status` | LLM backend health |

## LLM Routing

Priority: **Ollama (local, free) → OpenAI → Anthropic**

Set env vars to enable providers:
```bash
OLLAMA_BASE_URL=http://localhost:11434   # default, always tried first
OPENAI_API_KEY=sk-...                   # optional fallback
ANTHROPIC_API_KEY=sk-ant-...            # optional fallback
```

---

*LoveLogicAI LLC — Building what we survived.*

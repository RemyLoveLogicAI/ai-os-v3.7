"""
AI OS v3.7 — FastAPI Server
Production-grade REST API surface for the LLM Router + Skill Marketplace.

Endpoints:
  GET  /health              — System health + component status
  GET  /v1/info             — OS info and loaded skills
  POST /v1/route            — Route a prompt through the LLM Router
  POST /v1/complete         — Direct LLM completion (bypass routing logic)
  GET  /v1/skills           — List available skills
  GET  /v1/skills/{name}    — Get skill details
  POST /v1/skills/{name}/invoke — Invoke a skill
  GET  /v1/router/status    — LLM Router backend health
  POST /v1/router/reload    — Hot-reload router config
"""

import time
import logging
from contextlib import asynccontextmanager
from typing import Optional, Any

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.llm_router import LLMRouter, RouterConfig
from marketplace.registry import SkillRegistry

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("ai-os.api")

# ── App State ────────────────────────────────────────────────────────────────

router: LLMRouter = None
registry: SkillRegistry = None
startup_time: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global router, registry, startup_time

    log.info("[AI-OS] Initializing LLM Router...")
    router = LLMRouter(RouterConfig())
    await router.initialize()

    log.info("[AI-OS] Loading Skill Registry...")
    registry = SkillRegistry()
    await registry.load_all()

    startup_time = time.time()
    log.info(f"[AI-OS] Server ready — {len(registry.skills)} skills loaded")

    yield

    log.info("[AI-OS] Shutting down...")
    await router.shutdown()


# ── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI OS v3.7",
    description="LoveLogicAI — LLM Router + Skill Marketplace API",
    version="3.7.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──────────────────────────────────────────────────

class RouteRequest(BaseModel):
    prompt: str = Field(..., description="The prompt to route and complete")
    model_preference: Optional[str] = Field(None, description="Preferred model (optional)")
    system: Optional[str] = Field(None, description="System prompt override")
    max_tokens: int = Field(2048, ge=1, le=32768)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    stream: bool = Field(False, description="Stream response (future support)")
    metadata: dict = Field(default_factory=dict)


class CompleteRequest(BaseModel):
    model: str = Field(..., description="Exact model string to use")
    prompt: str
    system: Optional[str] = None
    max_tokens: int = Field(2048, ge=1, le=32768)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class SkillInvokeRequest(BaseModel):
    input: Any = Field(..., description="Skill input payload")
    context: dict = Field(default_factory=dict)


class RouteResponse(BaseModel):
    content: str
    model_used: str
    provider: str
    routed: bool
    latency_ms: float
    tokens_used: Optional[int] = None
    fallback_triggered: bool = False


# ── Dependency Injection ─────────────────────────────────────────────────────

def get_router() -> LLMRouter:
    if router is None:
        raise HTTPException(status_code=503, detail="LLM Router not initialized")
    return router


def get_registry() -> SkillRegistry:
    if registry is None:
        raise HTTPException(status_code=503, detail="Skill Registry not initialized")
    return registry


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
async def health():
    """System health check with component status."""
    uptime = time.time() - startup_time if startup_time else 0

    router_health = await router.health_check() if router else {"status": "not_initialized"}
    skill_count = len(registry.skills) if registry else 0

    return {
        "status": "healthy",
        "version": "3.7.0",
        "uptime_seconds": round(uptime, 2),
        "components": {
            "llm_router": router_health,
            "skill_registry": {
                "status": "healthy" if registry else "not_initialized",
                "skills_loaded": skill_count,
            }
        },
        "timestamp": time.time(),
    }


@app.get("/v1/info", tags=["System"])
async def info():
    """AI OS info and configuration."""
    return {
        "name": "AI OS",
        "version": "3.7.0",
        "operator": "LoveLogicAI LLC",
        "author": "Jeremy 'Remy' Morgan-Jones Sr.",
        "capabilities": ["llm-routing", "skill-marketplace", "fallback-chains"],
        "providers_configured": router.configured_providers() if router else [],
    }


@app.post("/v1/route", response_model=RouteResponse, tags=["LLM"])
async def route_prompt(
    req: RouteRequest,
    r: LLMRouter = Depends(get_router),
):
    """
    Route a prompt through the intelligent LLM Router.
    Automatically selects the best available backend with fallback chain.
    """
    start = time.time()

    try:
        result = await r.route(
            prompt=req.prompt,
            system=req.system,
            model_preference=req.model_preference,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
    except Exception as e:
        log.error(f"[ROUTE] Failed: {e}")
        raise HTTPException(status_code=502, detail=f"All LLM backends failed: {str(e)}")

    latency_ms = (time.time() - start) * 1000

    return RouteResponse(
        content=result["content"],
        model_used=result["model"],
        provider=result["provider"],
        routed=True,
        latency_ms=round(latency_ms, 2),
        tokens_used=result.get("tokens"),
        fallback_triggered=result.get("fallback", False),
    )


@app.post("/v1/complete", tags=["LLM"])
async def direct_complete(
    req: CompleteRequest,
    r: LLMRouter = Depends(get_router),
):
    """Direct completion — bypass routing, hit a specific model."""
    start = time.time()

    try:
        result = await r.complete_direct(
            model=req.model,
            prompt=req.prompt,
            system=req.system,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "content": result["content"],
        "model": req.model,
        "latency_ms": round((time.time() - start) * 1000, 2),
        "tokens_used": result.get("tokens"),
    }


@app.get("/v1/skills", tags=["Skills"])
async def list_skills(reg: SkillRegistry = Depends(get_registry)):
    """List all available skills in the marketplace."""
    return {
        "skills": [s.to_dict() for s in reg.skills.values()],
        "total": len(reg.skills),
    }


@app.get("/v1/skills/{skill_name}", tags=["Skills"])
async def get_skill(skill_name: str, reg: SkillRegistry = Depends(get_registry)):
    """Get details for a specific skill."""
    skill = reg.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    return skill.to_dict()


@app.post("/v1/skills/{skill_name}/invoke", tags=["Skills"])
async def invoke_skill(
    skill_name: str,
    req: SkillInvokeRequest,
    reg: SkillRegistry = Depends(get_registry),
):
    """Invoke a skill from the marketplace."""
    skill = reg.get(skill_name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")

    start = time.time()
    try:
        result = await skill.invoke(req.input, context=req.context)
    except Exception as e:
        log.error(f"[SKILL:{skill_name}] Invocation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "skill": skill_name,
        "result": result,
        "latency_ms": round((time.time() - start) * 1000, 2),
    }


@app.get("/v1/router/status", tags=["Router"])
async def router_status(r: LLMRouter = Depends(get_router)):
    """Get LLM Router backend health and configuration."""
    return await r.status()


@app.post("/v1/router/reload", tags=["Router"])
async def router_reload(r: LLMRouter = Depends(get_router)):
    """Hot-reload router configuration without restarting the server."""
    await r.reload_config()
    return {"status": "reloaded", "timestamp": time.time()}


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    log.error(f"[AI-OS] Unhandled exception on {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )

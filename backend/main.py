"""NeuroFence FastAPI Application.

Production-grade wiring:
- Loads settings from .env / environment.
- Creates SQLAlchemy engine + schema (idempotent).
- Initializes detector, isolation engine, interceptor.

Run:
  python -m uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import get_settings
from backend.db import create_database, ensure_schema, db_session
from backend.models.detector import SimpleDetector
from backend.models.isolation import SimpleIsolationEngine
from backend.models.interceptor import MessageInterceptor


settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("neurofence")


app = FastAPI(
    title="NeuroFence",
    description="AI Agent Safety System - Real-time Contamination Detection",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class InterceptRequest(BaseModel):
    sender: str
    recipient: str
    content: str


class InterceptResponse(BaseModel):
    allowed: bool
    action: str
    reason: str
    score: float
    layers: Dict[str, Any]
    agent_isolated: Optional[str] = None
    flagged: Optional[bool] = False


class IsolateRequest(BaseModel):
    reason: str


class ReleaseResponse(BaseModel):
    success: bool
    agent: str
    message: str


class StatsResponse(BaseModel):
    total_isolated_active: int
    isolated_agents: List[str]
    total_blocks_all_time: int
    total_unique_agents_isolated: int


class UpdateBaselineRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def initialize_components() -> None:
    db = create_database(settings.database_url)
    ensure_schema(db)

    detector = SimpleDetector(
        model_name=settings.embedding_model,
        agent_baselines_table=db.tables.get("agent_baselines"),
    )

    # Load persisted baselines, if any
    try:
        with db_session(db) as session:
            detector.load_baselines_from_db(session)
    except Exception:
        logger.debug("Baseline load failed; continuing with empty baselines", exc_info=True)

    isolation_engine = SimpleIsolationEngine(db)
    interceptor = MessageInterceptor(detector, isolation_engine, settings)

    app.state.db = db
    app.state.detector = detector
    app.state.isolation_engine = isolation_engine
    app.state.interceptor = interceptor


@app.on_event("startup")
async def startup() -> None:
    logger.info("=" * 60)
    logger.info("🚀 NeuroFence Starting Up...")
    logger.info("=" * 60)
    try:
        initialize_components()
        logger.info("✅ All components initialized successfully!")
    except Exception:
        logger.exception("❌ Initialization failed")
        # Keep app up for /health, but mark components as missing
        app.state.db = None
        app.state.detector = None
        app.state.isolation_engine = None
        app.state.interceptor = None


@app.on_event("shutdown")
async def shutdown() -> None:
    db = getattr(app.state, "db", None)
    if db is not None:
        try:
            db.engine.dispose()
        except Exception:
            logger.debug("Engine dispose failed", exc_info=True)
    logger.info("✅ Application shutdown")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> Dict[str, Any]:
    interceptor = getattr(app.state, "interceptor", None)
    isolation_engine = getattr(app.state, "isolation_engine", None)
    detector = getattr(app.state, "detector", None)

    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "detector": "ready" if detector else "not_ready",
        "isolation_engine": "ready" if isolation_engine else "not_ready",
        "interceptor": "ready" if interceptor else "not_ready",
    }


@app.post("/intercept", response_model=InterceptResponse)
async def intercept_message(request: InterceptRequest) -> Dict[str, Any]:
    interceptor: Optional[MessageInterceptor] = getattr(app.state, "interceptor", None)
    if interceptor is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    return interceptor.intercept(request.sender, request.recipient, request.content)


@app.post("/isolate/{agent_name}", response_model=ReleaseResponse)
async def isolate_agent(agent_name: str, request: IsolateRequest) -> Dict[str, Any]:
    isolation_engine: Optional[SimpleIsolationEngine] = getattr(app.state, "isolation_engine", None)
    if isolation_engine is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    if isolation_engine.is_isolated(agent_name):
        raise HTTPException(status_code=400, detail=f"{agent_name} is already isolated")

    success = isolation_engine.isolate(agent_name, request.reason)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to isolate agent")

    return {"success": True, "agent": agent_name, "message": f"Agent {agent_name} isolated"}


@app.post("/release/{agent_name}", response_model=ReleaseResponse)
async def release_agent(agent_name: str) -> Dict[str, Any]:
    isolation_engine: Optional[SimpleIsolationEngine] = getattr(app.state, "isolation_engine", None)
    if isolation_engine is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    if not isolation_engine.is_isolated(agent_name):
        raise HTTPException(status_code=400, detail=f"{agent_name} is not currently isolated")

    success = isolation_engine.release(agent_name)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to release agent")

    return {"success": True, "agent": agent_name, "message": f"Agent {agent_name} released"}


@app.get("/stats", response_model=StatsResponse)
async def get_stats() -> Dict[str, Any]:
    isolation_engine: Optional[SimpleIsolationEngine] = getattr(app.state, "isolation_engine", None)
    if isolation_engine is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    return isolation_engine.get_stats()


@app.get("/forensics/{agent_name}")
async def get_forensics(agent_name: str) -> Dict[str, Any]:
    isolation_engine: Optional[SimpleIsolationEngine] = getattr(app.state, "isolation_engine", None)
    if isolation_engine is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    return isolation_engine.get_forensics(agent_name)


@app.post("/update-baseline/{agent_name}")
async def update_baseline(agent_name: str, request: UpdateBaselineRequest) -> Dict[str, Any]:
    interceptor: Optional[MessageInterceptor] = getattr(app.state, "interceptor", None)
    detector: Optional[SimpleDetector] = getattr(app.state, "detector", None)

    if interceptor is None or detector is None:
        raise HTTPException(status_code=503, detail="System not initialized")

    success = interceptor.update_agent_baseline(agent_name, request.content)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update baseline")

    return {"success": True, "agent": agent_name, "message": f"Baseline updated for {agent_name}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.api_host,
        port=int(settings.api_port),
        reload=bool(settings.debug),
    )

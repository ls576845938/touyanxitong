from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.agent.api import router as agent_router
from app.agent.mcp_router import mcp_router
from app.api.routes_chain import router as chain_router
from app.api.routes_industry import router as industry_router
from app.api.routes_market import router as market_router
from app.api.routes_research import router as research_router
from app.api.routes_reports import router as reports_router
from app.api.routes_retail import router as retail_router
from app.api.routes_stocks import router as stocks_router
from app.api.routes_tenbagger import router as tenbagger_router
from app.api.routes_watchlist import router as watchlist_router
from app.config import settings
from app.db.session import database_url, get_database_info, init_db


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    if settings.auto_run_pipeline_on_startup:
        from app.pipeline.daily_pipeline import run_daily_pipeline

        logger.info("AUTO_RUN_PIPELINE_ON_STARTUP enabled; running MVP pipeline")
        run_daily_pipeline()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="AI 产业趋势雷达与十倍股早期特征发现系统。研究辅助，不提供投资建议。",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, object]:
    db_info = get_database_info()
    return {
        "status": "ok",
        "app": settings.app_name,
        "database_url": database_url,
        "database_dialect": db_info["dialect"],
        "database_path": db_info["path"],
        "schema_version": db_info["schema_version"],
        "schema_expected_version": db_info["expected_schema_version"],
        "schema_current": db_info["schema_current"],
        "database_available": db_info["available"],
    }


app.include_router(market_router)
app.include_router(industry_router)
app.include_router(chain_router)
app.include_router(stocks_router)
app.include_router(reports_router)
app.include_router(watchlist_router)
app.include_router(research_router)
app.include_router(tenbagger_router)
app.include_router(retail_router)
app.include_router(agent_router)
app.include_router(mcp_router)

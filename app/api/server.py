"""FastAPI 服务入口。"""

from __future__ import annotations

from fastapi import FastAPI

from app.api.routes.agent import router as agent_router
from app.api.routes.debug import router as debug_router
from app.core.config import settings


def create_app() -> FastAPI:
    """创建 FastAPI 应用。"""
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        description="SimpleCodeAgent 的 HTTP 服务接口。",
    )
    app.include_router(agent_router)
    app.include_router(debug_router)
    return app


app = create_app()

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import router
from app.db.repo import init_db
from app.middleware.observability import ObservabilityMiddleware
from app.infra.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(ObservabilityMiddleware)
    app.include_router(router)

    return app


app = create_app()

from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.api.routes import router
from app.db.repo import close_db, init_db
from app.infra.container import close_runtime, init_runtime
from app.middleware.observability import ObservabilityMiddleware
from app.infra.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await init_runtime()
    yield
    await close_runtime()
    await close_db()


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(ObservabilityMiddleware)
    app.include_router(router)

    return app


app = create_app()

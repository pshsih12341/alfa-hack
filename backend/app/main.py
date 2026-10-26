import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import admin, applications, users
from .scoring import rescore_stuck

logger = logging.getLogger(__name__)

RESCORE_INTERVAL_SECONDS = 30


async def _rescore_loop() -> None:
    """Раз в RESCORE_INTERVAL_SECONDS скорит заявки, застрявшие в PRESCORING (ML был недоступен)."""
    while True:
        await asyncio.sleep(RESCORE_INTERVAL_SECONDS)
        try:
            scored = await asyncio.to_thread(rescore_stuck)
            if scored:
                logger.info("Повторный скоринг: решение получили %s заявок", scored)
        except Exception:
            logger.exception("Повторный скоринг упал")


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_rescore_loop()) if config.settings.SCORING_MODE == "ml" else None
    yield
    if task is not None:
        task.cancel()


app = FastAPI(title="Credit Kiosk API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in config.settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(users.router)
app.include_router(applications.router)
app.include_router(admin.router)


@app.get("/", include_in_schema=False)
def root():
    return {"detail": "API only. See /docs"}

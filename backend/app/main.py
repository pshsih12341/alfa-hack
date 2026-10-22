from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, database, routers

app = FastAPI(title="Кредитный кабинет для СМИ", version="0.1.0")

# CORS — для отдельно запускаемого фронтенда.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routers.users.router)

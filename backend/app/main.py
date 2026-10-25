from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routers import admin, applications, users

app = FastAPI(title="Credit Kiosk API")

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
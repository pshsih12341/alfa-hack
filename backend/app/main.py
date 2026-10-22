from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from . import database, routers

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Кредитный кабинет для СМИ", version="0.1.0")

    # БД создаётся на старте (удобно для SQLite).
    database.Base.metadata.create_all(bind=database.engine)

    app.include_router(routers.users.router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    return app


app = create_app()

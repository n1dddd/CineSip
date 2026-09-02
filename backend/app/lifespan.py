from contextlib import asynccontextmanager

from dotenv import load_dotenv

from app.database import close_db, init_db


@asynccontextmanager
async def lifespan(app):
    """Open the SQLite connection on boot, close it on shutdown.

    .env is loaded here rather than at import time; database.py resolves
    DB_PATH lazily, so env vars are read after this runs.
    """
    load_dotenv()
    await init_db()
    yield
    await close_db()

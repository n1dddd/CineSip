from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

load_dotenv()

from app.database import init_db, close_db


@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield
    await close_db()
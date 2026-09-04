import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.lifespan import lifespan
from app.routes import game, lobby, movies

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(
    title="CineSip",
    description="Movie drinking game — pick a movie, get AI-generated drinking rules, play with friends.",
    version="0.1.0",
    lifespan=lifespan,
)

# Same-origin in production (nginx proxies /api/), so credentials are never
# needed cross-origin. allow_origins=["*"] WITH allow_credentials=True is an
# invalid combination browsers reject outright.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lobby.router)
app.include_router(game.router)
app.include_router(movies.router)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "cinesip"}


@app.get("/api/health")
async def api_health():
    """Same health check, reachable through the nginx /api/ proxy."""
    return {"status": "ok", "service": "cinesip"}
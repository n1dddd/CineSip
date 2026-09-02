import os
import httpx

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")


async def search_movies(query: str, page: int = 1) -> dict:
    """Search TMDB for movies by title."""
    if not TMDB_API_KEY or TMDB_API_KEY.startswith("your_"):
        return {"results": [], "error": "TMDB API key not configured"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE}/search/movie",
            params={"api_key": TMDB_API_KEY, "query": query, "page": page},
        )
        resp.raise_for_status()
        return resp.json()


async def get_movie_details(movie_id: int) -> dict:
    """Get full movie details by TMDB ID."""
    if not TMDB_API_KEY or TMDB_API_KEY.startswith("your_"):
        return {"error": "TMDB API key not configured"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE}/movie/{movie_id}",
            params={"api_key": TMDB_API_KEY, "append_to_response": "credits"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_popular_movies(page: int = 1) -> dict:
    """Get popular movies."""
    if not TMDB_API_KEY or TMDB_API_KEY.startswith("your_"):
        return {"results": [], "error": "TMDB API key not configured"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{TMDB_BASE}/movie/popular",
            params={"api_key": TMDB_API_KEY, "page": page},
        )
        resp.raise_for_status()
        return resp.json()
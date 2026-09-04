import logging
import os

import httpx

log = logging.getLogger("cinesip.tmdb")

TMDB_BASE = "https://api.themoviedb.org/3"
_TIMEOUT = 12.0


def _api_key() -> str:
    """Read lazily so .env load order cannot silently disable TMDB."""
    return os.getenv("TMDB_API_KEY", "")


def _unconfigured() -> bool:
    key = _api_key()
    return not key or key.startswith("your_")


async def _get(path: str, params: dict) -> dict:
    """GET a TMDB endpoint, returning {'error': ...} instead of raising."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{TMDB_BASE}{path}", params={**params, "api_key": _api_key()})
        if resp.status_code != 200:
            log.warning("tmdb: %s HTTP %s: %s", path, resp.status_code, resp.text[:200])
            return {"error": f"TMDB returned {resp.status_code}"}
        return resp.json()
    except httpx.HTTPError as exc:
        log.warning("tmdb: %s transport error: %s: %s", path, type(exc).__name__, exc)
        return {"error": "TMDB is unreachable right now"}
    except ValueError:
        log.warning("tmdb: %s returned non-JSON", path)
        return {"error": "TMDB returned a malformed response"}


async def search_movies(query: str, page: int = 1) -> dict:
    """Search TMDB for movies by title."""
    if _unconfigured():
        return {"results": [], "error": "TMDB API key not configured"}
    result = await _get("/search/movie", {"query": query, "page": page})
    result.setdefault("results", [])
    return result


async def get_movie_details(movie_id: int) -> dict:
    """Get full movie details, including the fields rule generation needs.

    `keywords` and `credits` come back in one request via append_to_response.
    Note the movie namespace nests as keywords.keywords[] (NOT .results[],
    which is the TV shape — getting it wrong silently yields an empty list).
    """
    if _unconfigured():
        return {"error": "TMDB API key not configured"}
    return await _get(
        f"/movie/{movie_id}",
        {"language": "en-US", "append_to_response": "keywords,credits"},
    )


async def get_popular_movies(page: int = 1) -> dict:
    """Get popular movies."""
    if _unconfigured():
        return {"results": [], "error": "TMDB API key not configured"}
    result = await _get("/movie/popular", {"page": page})
    result.setdefault("results", [])
    return result

from fastapi import APIRouter, HTTPException

from app.services import movie_search

router = APIRouter(prefix="/api/movies", tags=["movies"])


@router.get("/search")
async def search_movies(q: str, page: int = 1):
    """Search TMDB for movies."""
    result = await movie_search.search_movies(q, page)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/popular")
async def popular_movies(page: int = 1):
    """Get popular movies from TMDB."""
    result = await movie_search.get_popular_movies(page)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/{movie_id}")
async def movie_details(movie_id: int):
    """Get movie details by TMDB ID."""
    result = await movie_search.get_movie_details(movie_id)
    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])
    return result
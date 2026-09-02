from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import AddRuleRequest, DrinkLogOut, LogDrinkRequest, RuleOut
from app.services import game_manager, movie_search, rule_generator

router = APIRouter(prefix="/api/games", tags=["game"])


class SelectMovieRequest(BaseModel):
    movie_id: int
    movie_title: str


@router.post("/{game_id}/movie", status_code=200)
async def select_movie(game_id: int, req: SelectMovieRequest):
    """Attach a TMDB movie to the game and generate grounded drinking rules.

    Rules are generated from REAL TMDB data (overview, genres, cast), never from
    LLM training memory — so brand-new releases work and rules can't be hallucinated.
    """
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    details = await movie_search.get_movie_details(req.movie_id)
    if "error" in details:
        raise HTTPException(status_code=503, detail=details["error"])

    overview = details.get("overview") or ""
    genres = ", ".join(g["name"] for g in details.get("genres", []))
    cast = ", ".join(
        c["name"] for c in (details.get("credits", {}).get("cast", [])[:8])
    )
    plot_context = overview
    if cast:
        plot_context += f"\n\nMain cast: {cast}"

    rules = await rule_generator.generate_rules(
        movie_title=req.movie_title,
        genre=genres,
        plot_summary=plot_context,
    )

    await game_manager.set_movie(game_id, req.movie_title, req.movie_id)
    await game_manager.clear_rules(game_id)
    created = [
        await game_manager.add_rule(game_id, r["team"], r["description"])
        for r in rules
    ]
    return {"movie_title": req.movie_title, "rules": created}


@router.post("/{game_id}/rules", response_model=RuleOut, status_code=201)
async def add_rule(game_id: int, req: AddRuleRequest):
    """Add a drinking rule to a game."""
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return await game_manager.add_rule(game_id, req.team, req.description)


@router.post("/{game_id}/drinks", response_model=DrinkLogOut, status_code=201)
async def log_drink(game_id: int, req: LogDrinkRequest):
    """Log a drink for a player triggered by a rule."""
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return await game_manager.log_drink(req.player_id, req.rule_id)
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.models import AddRuleRequest, DrinkLogOut, LogDrinkRequest, RuleOut
from app.services import (
    film_context,
    game_manager,
    movie_search,
    rule_generator,
    wiki_plot,
)

log = logging.getLogger("cinesip.game")

router = APIRouter(prefix="/api/games", tags=["game"])


class SelectMovieRequest(BaseModel):
    movie_id: int
    movie_title: str


async def _generate_and_store(game_id: int, movie_id: int, details: dict) -> None:
    """Background: enrich context, generate rules, swap them in atomically.

    Runs after the HTTP response so the phone never waits on the LLM. The
    lobby already polls every 2s and shows a "Writing rules…" state.
    """
    try:
        plot = await wiki_plot.get_plot(movie_id)
        ctx = film_context.build_film_context(details, plot)
        rules = await rule_generator.generate_rules(ctx)
        await game_manager.replace_rules(game_id, rules)
        await game_manager.set_rules_status(game_id, "ready")
        log.info(
            "rulegen: stored %d rules for game=%s title=%r",
            len(rules), game_id, ctx.get("title"),
        )
    except Exception:
        log.exception("rulegen: background task failed for game=%s", game_id)
        await game_manager.set_rules_status(game_id, "error")


@router.post("/{game_id}/movie", status_code=202)
async def select_movie(game_id: int, req: SelectMovieRequest, bg: BackgroundTasks):
    """Attach a TMDB movie to the game and kick off rule generation.

    Returns 202 immediately — rules land asynchronously and the lobby polls for
    them. Rules are generated from REAL fetched data (TMDB credits/keywords plus
    the Wikipedia plot section), never from LLM training memory, so brand-new
    releases work and rules cannot be hallucinated.
    """
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    # Re-picking a film deletes rules, and drink_logs cascade off rules — so
    # changing the film mid-game would silently wipe every logged sip.
    if game.status != "lobby":
        raise HTTPException(
            status_code=409,
            detail="The film can't be changed once the game has started",
        )

    details = await movie_search.get_movie_details(req.movie_id)
    if "error" in details:
        raise HTTPException(status_code=503, detail=details["error"])

    await game_manager.set_movie(game_id, req.movie_title, req.movie_id)
    await game_manager.clear_rules(game_id)
    await game_manager.set_rules_status(game_id, "generating")
    bg.add_task(_generate_and_store, game_id, req.movie_id, details)

    return {"movie_title": req.movie_title, "rules": [], "rules_status": "generating"}


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
    if not await game_manager.owns_player_and_rule(game_id, req.player_id, req.rule_id):
        raise HTTPException(
            status_code=400, detail="Player or rule does not belong to this game"
        )
    return await game_manager.log_drink(req.player_id, req.rule_id)

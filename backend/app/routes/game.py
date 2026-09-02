from fastapi import APIRouter, HTTPException
from app.models import AddRuleRequest, LogDrinkRequest, RuleOut, DrinkLogOut
from app.services import game_manager

router = APIRouter(prefix="/api/games", tags=["game"])


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
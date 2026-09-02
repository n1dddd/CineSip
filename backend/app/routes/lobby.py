from fastapi import APIRouter, HTTPException
from app.models import CreateGameRequest, JoinGameRequest, GameOut, PlayerOut, GameState
from app.services import game_manager

router = APIRouter(prefix="/api", tags=["lobby"])


@router.post("/games", response_model=GameOut, status_code=201)
async def create_game(req: CreateGameRequest):
    """Create a new game lobby."""
    return await game_manager.create_game(
        movie_title=req.movie_title,
        movie_id=req.movie_id,
    )


@router.post("/games/join", response_model=PlayerOut, status_code=201)
async def join_game(req: JoinGameRequest):
    """Join an existing game by code."""
    try:
        return await game_manager.join_game(code=req.code, name=req.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/games/{code}", response_model=GameState)
async def get_game_state(code: str):
    """Get full game state by join code."""
    game = await game_manager.get_game_by_code(code)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    state = await game_manager.get_game_state(game.id)
    if state is None:
        raise HTTPException(status_code=404, detail="Game state not found")
    return state


@router.post("/games/{game_id}/start", response_model=GameOut)
async def start_game(game_id: int):
    """Start the game (change status from lobby to active)."""
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return await game_manager.start_game(game_id)


@router.post("/games/{game_id}/finish", response_model=GameOut)
async def finish_game(game_id: int):
    """Finish the game."""
    game = await game_manager.get_game_by_id(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")
    return await game_manager.finish_game(game_id)

from pydantic import BaseModel, Field

# ── Request models ──

class CreateGameRequest(BaseModel):
    movie_title: str | None = None
    movie_id: int | None = None


class JoinGameRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    name: str = Field(min_length=1, max_length=30)


class AddRuleRequest(BaseModel):
    game_id: int
    team: int = Field(ge=0, le=1)
    description: str = Field(min_length=1, max_length=200)


class LogDrinkRequest(BaseModel):
    player_id: int
    rule_id: int


class StartGameRequest(BaseModel):
    game_id: int


# ── Response models ──

class GameOut(BaseModel):
    id: int
    code: str
    movie_title: str | None
    movie_id: int | None
    status: str
    created_at: str


class PlayerOut(BaseModel):
    id: int
    game_id: int
    name: str
    team: int
    is_host: bool
    joined_at: str


class RuleOut(BaseModel):
    id: int
    game_id: int
    team: int
    description: str
    trigger_count: int


class DrinkLogOut(BaseModel):
    id: int
    player_id: int
    rule_id: int
    timestamp: str


class GameState(BaseModel):
    game: GameOut
    players: list[PlayerOut]
    rules: list[RuleOut]
    drink_logs: list[DrinkLogOut]
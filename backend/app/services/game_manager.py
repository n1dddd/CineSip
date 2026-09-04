import random
import string

from app.database import get_db
from app.models import DrinkLogOut, GameOut, GameState, PlayerOut, RuleOut


def _generate_code() -> str:
    """Generate a 6-character uppercase alphanumeric join code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


async def create_game(movie_title: str | None = None, movie_id: int | None = None) -> GameOut:
    """Create a new game with a unique join code."""
    db = await get_db()
    code = _generate_code()
    # Ensure uniqueness
    while True:
        cursor = await db.execute("SELECT 1 FROM games WHERE code = ?", (code,))
        if await cursor.fetchone() is None:
            break
        code = _generate_code()

    cursor = await db.execute(
        "INSERT INTO games (code, movie_title, movie_id) VALUES (?, ?, ?)",
        (code, movie_title, movie_id),
    )
    await db.commit()
    row = await db.execute("SELECT * FROM games WHERE id = ?", (cursor.lastrowid,))
    game = await row.fetchone()
    return GameOut(**dict(game))


async def get_game_by_code(code: str) -> GameOut | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM games WHERE code = ?", (code.upper(),))
    row = await cursor.fetchone()
    return GameOut(**dict(row)) if row else None


async def get_game_by_id(game_id: int) -> GameOut | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM games WHERE id = ?", (game_id,))
    row = await cursor.fetchone()
    return GameOut(**dict(row)) if row else None


async def join_game(code: str, name: str) -> PlayerOut:
    """Add a player to a game. First player is host. Auto-assign team for balance."""
    db = await get_db()
    game = await get_game_by_code(code)
    if game is None:
        raise ValueError(f"Game with code {code} not found")
    if game.status != "lobby":
        raise ValueError("Game has already started or finished")

    # Count existing players per team for auto-balance
    cursor = await db.execute(
        "SELECT team, COUNT(*) as cnt FROM players WHERE game_id = ? GROUP BY team",
        (game.id,),
    )
    team_counts = {0: 0, 1: 0}
    async for row in cursor:
        team_counts[row["team"]] = row["cnt"]

    # Assign to smaller team
    team = 0 if team_counts[0] <= team_counts[1] else 1

    # First player is host
    cursor = await db.execute(
        "SELECT COUNT(*) as cnt FROM players WHERE game_id = ?", (game.id,)
    )
    row = await cursor.fetchone()
    is_host = row["cnt"] == 0

    cursor = await db.execute(
        "INSERT INTO players (game_id, name, team, is_host) VALUES (?, ?, ?, ?)",
        (game.id, name, team, int(is_host)),
    )
    await db.commit()

    cursor = await db.execute("SELECT * FROM players WHERE id = ?", (cursor.lastrowid,))
    row = await cursor.fetchone()
    d = dict(row)
    d["is_host"] = bool(d["is_host"])
    return PlayerOut(**d)


async def start_game(game_id: int) -> GameOut:
    db = await get_db()
    await db.execute(
        "UPDATE games SET status = 'active' WHERE id = ? AND status = 'lobby'",
        (game_id,),
    )
    await db.commit()
    return await get_game_by_id(game_id)


async def finish_game(game_id: int) -> GameOut:
    db = await get_db()
    await db.execute(
        "UPDATE games SET status = 'finished' WHERE id = ?",
        (game_id,),
    )
    await db.commit()
    return await get_game_by_id(game_id)


async def set_movie(game_id: int, movie_title: str, movie_id: int) -> GameOut | None:
    """Attach a TMDB movie to an existing game."""
    db = await get_db()
    await db.execute(
        "UPDATE games SET movie_title = ?, movie_id = ? WHERE id = ?",
        (movie_title, movie_id, game_id),
    )
    await db.commit()
    return await get_game_by_id(game_id)


async def clear_rules(game_id: int) -> None:
    """Remove all rules for a game (used when re-picking a movie).

    drink_logs.rule_id is ON DELETE CASCADE, so this destroys the score. Only
    safe while the game is still in the lobby — the route enforces that.
    """
    db = await get_db()
    await db.execute("DELETE FROM rules WHERE game_id = ?", (game_id,))
    await db.commit()


async def replace_rules(game_id: int, rules: list[dict]) -> list[RuleOut]:
    """Atomically swap in a new rule set. One transaction, one commit."""
    db = await get_db()
    await db.execute("DELETE FROM rules WHERE game_id = ?", (game_id,))
    await db.executemany(
        "INSERT INTO rules (game_id, team, description) VALUES (?, ?, ?)",
        [(game_id, r["team"], r["description"]) for r in rules],
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM rules WHERE game_id = ? ORDER BY id", (game_id,)
    )
    return [RuleOut(**dict(r)) async for r in cursor]


async def set_rules_status(game_id: int, status: str) -> None:
    """Track rule generation: idle | generating | ready | fallback | error."""
    db = await get_db()
    await db.execute(
        "UPDATE games SET rules_status = ? WHERE id = ?", (status, game_id)
    )
    await db.commit()


async def add_rule(game_id: int, team: int, description: str) -> RuleOut:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO rules (game_id, team, description) VALUES (?, ?, ?)",
        (game_id, team, description),
    )
    await db.commit()
    cursor = await db.execute("SELECT * FROM rules WHERE id = ?", (cursor.lastrowid,))
    row = await cursor.fetchone()
    return RuleOut(**dict(row))


async def owns_player_and_rule(game_id: int, player_id: int, rule_id: int) -> bool:
    """Verify both the player and the rule belong to this game before logging."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT
             (SELECT COUNT(*) FROM players WHERE id = ? AND game_id = ?) AS p,
             (SELECT COUNT(*) FROM rules   WHERE id = ? AND game_id = ?) AS r""",
        (player_id, game_id, rule_id, game_id),
    )
    row = await cursor.fetchone()
    return bool(row and row["p"] and row["r"])


async def log_drink(player_id: int, rule_id: int) -> DrinkLogOut:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO drink_logs (player_id, rule_id) VALUES (?, ?)",
        (player_id, rule_id),
    )
    # Increment rule trigger count
    await db.execute(
        "UPDATE rules SET trigger_count = trigger_count + 1 WHERE id = ?", (rule_id,)
    )
    await db.commit()
    cursor = await db.execute("SELECT * FROM drink_logs WHERE id = ?", (cursor.lastrowid,))
    row = await cursor.fetchone()
    return DrinkLogOut(**dict(row))


async def get_game_state(game_id: int) -> GameState | None:
    game = await get_game_by_id(game_id)
    if game is None:
        return None
    db = await get_db()

    players_cursor = await db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY joined_at", (game_id,)
    )
    players = [PlayerOut(**{**dict(r), "is_host": bool(r["is_host"])}) async for r in players_cursor]

    rules_cursor = await db.execute(
        "SELECT * FROM rules WHERE game_id = ? ORDER BY id", (game_id,)
    )
    rules = [RuleOut(**dict(r)) async for r in rules_cursor]

    logs_cursor = await db.execute(
        """SELECT dl.* FROM drink_logs dl
           JOIN players p ON dl.player_id = p.id
           WHERE p.game_id = ? ORDER BY dl.timestamp""",
        (game_id,),
    )
    drink_logs = [DrinkLogOut(**dict(r)) async for r in logs_cursor]

    return GameState(game=game, players=players, rules=rules, drink_logs=drink_logs)


async def get_players(game_id: int) -> list[PlayerOut]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY joined_at", (game_id,)
    )
    return [PlayerOut(**{**dict(r), "is_host": bool(r["is_host"])}) async for r in cursor]
import os

import aiosqlite

_db: aiosqlite.Connection | None = None

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cinesip.db")


def db_path() -> str:
    """Resolve the database path at call time, not import time.

    Reading DB_PATH lazily means .env can be loaded after this module is
    imported (the container sets DB_PATH=/app/data/cinesip.db).
    """
    return os.environ.get("DB_PATH", _DEFAULT_DB)


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(db_path())
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    db = await get_db()
    await db.executescript(
        """
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            movie_title TEXT,
            movie_id INTEGER,
            status TEXT NOT NULL DEFAULT 'lobby' CHECK(status IN ('lobby','active','finished')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            team INTEGER NOT NULL DEFAULT 0 CHECK(team IN (0, 1)),
            is_host INTEGER NOT NULL DEFAULT 0,
            joined_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            team INTEGER NOT NULL CHECK(team IN (0, 1)),
            description TEXT NOT NULL,
            trigger_count INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS drink_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            rule_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY (rule_id) REFERENCES rules(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_players_game ON players(game_id);
        CREATE INDEX IF NOT EXISTS idx_rules_game ON rules(game_id);
        CREATE INDEX IF NOT EXISTS idx_drink_logs_player ON drink_logs(player_id);
        """
    )
    await db.commit()


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None
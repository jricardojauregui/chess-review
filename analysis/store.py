"""SQLite storage: imported games, cached engine analyses, player profiles.

The analysis cache key is (hash of the PGN, depth), so a game is only ever
sent to Stockfish once per depth. Classification is NOT cached: it is cheap
and recomputed on every load, so changing thresholds in config.py takes
effect immediately.
"""
import hashlib
import json
import sqlite3
import time

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id        TEXT PRIMARY KEY,      -- hash of the PGN
    pgn       TEXT NOT NULL,
    meta      TEXT NOT NULL,         -- JSON: players, ratings, result...
    username  TEXT,                  -- chess.com user it was fetched for (lowercase)
    end_time  INTEGER,
    created   REAL
);
CREATE INDEX IF NOT EXISTS games_user ON games (username, end_time);
CREATE TABLE IF NOT EXISTS analyses (
    game_id   TEXT NOT NULL,
    depth     INTEGER NOT NULL,
    positions TEXT NOT NULL,         -- JSON: raw engine output per position
    created   REAL,
    PRIMARY KEY (game_id, depth)
);
CREATE TABLE IF NOT EXISTS settings (
    key       TEXT PRIMARY KEY,
    value     TEXT NOT NULL          -- JSON
);
CREATE TABLE IF NOT EXISTS players (
    username  TEXT PRIMARY KEY,
    data      TEXT NOT NULL,
    fetched   REAL
);
"""


def _connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def pgn_hash(pgn):
    """Stable id for a game: hash of its (whitespace-normalised) PGN."""
    normalised = " ".join(pgn.split())
    return hashlib.sha1(normalised.encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ games
def save_games(items):
    """Insert/refresh many games in one transaction.

    ``items`` is an iterable of ``(pgn, meta, username, end_time)``.
    Returns the list of game ids, in order.
    """
    rows, ids = [], []
    now = time.time()
    for pgn, meta, username, end_time in items:
        game_id = pgn_hash(pgn)
        ids.append(game_id)
        rows.append((game_id, pgn, json.dumps(meta),
                     username.lower() if username else None, end_time, now))
    with _connect() as conn:
        conn.executemany(
            """INSERT INTO games (id, pgn, meta, username, end_time, created)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   meta = excluded.meta,
                   username = COALESCE(excluded.username, games.username),
                   end_time = COALESCE(excluded.end_time, games.end_time)""",
            rows,
        )
    return ids


def save_game(pgn, meta, username=None, end_time=None):
    """Insert a game (or refresh its metadata) and return its id."""
    return save_games([(pgn, meta, username, end_time)])[0]


def _game_row(row):
    game = dict(row)
    game["meta"] = json.loads(game["meta"])
    return game


def get_game(game_id):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    return _game_row(row) if row else None


def games_for_user(username, limit=None, analysed_only=False):
    """Most recent stored games of a chess.com user."""
    sql = "SELECT g.* FROM games g WHERE g.username = ?"
    if analysed_only:
        sql += " AND EXISTS (SELECT 1 FROM analyses a WHERE a.game_id = g.id)"
    sql += " ORDER BY g.end_time DESC"
    params = [username.lower()]
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    with _connect() as conn:
        return [_game_row(r) for r in conn.execute(sql, params).fetchall()]


# --------------------------------------------------------------- analyses
def save_analysis(game_id, depth, positions):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyses (game_id, depth, positions, created) VALUES (?, ?, ?, ?)",
            (game_id, int(depth), json.dumps(positions), time.time()),
        )


def delete_analysis(game_id, depth):
    with _connect() as conn:
        conn.execute("DELETE FROM analyses WHERE game_id = ? AND depth = ?", (game_id, int(depth)))


def get_analysis(game_id, depth):
    with _connect() as conn:
        row = conn.execute(
            "SELECT positions FROM analyses WHERE game_id = ? AND depth = ?",
            (game_id, int(depth)),
        ).fetchone()
    return json.loads(row["positions"]) if row else None


def analysed_depths(game_id):
    """Depths already analysed for a game, deepest first."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT depth FROM analyses WHERE game_id = ? ORDER BY depth DESC", (game_id,)
        ).fetchall()
    return [r["depth"] for r in rows]


def analysed_game_ids(game_ids):
    """Subset of ``game_ids`` with at least one cached analysis -> max depth."""
    if not game_ids:
        return {}
    marks = ",".join("?" * len(game_ids))
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT game_id, MAX(depth) AS depth FROM analyses WHERE game_id IN ({marks}) GROUP BY game_id",
            list(game_ids),
        ).fetchall()
    return {r["game_id"]: r["depth"] for r in rows}


# ---------------------------------------------------------------- players
def get_player(username, max_age=7 * 86400):
    with _connect() as conn:
        row = conn.execute(
            "SELECT data, fetched FROM players WHERE username = ?", (username.lower(),)
        ).fetchone()
    if row and time.time() - row["fetched"] < max_age:
        return json.loads(row["data"])
    return None


def save_player(username, data):
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO players (username, data, fetched) VALUES (?, ?, ?)",
            (username.lower(), json.dumps(data), time.time()),
        )


# --------------------------------------------------------------- settings
DEFAULT_SETTINGS = {
    "account": None,        # {"username", "avatar", "name"} of the linked chess.com account
    "theme": "dark",        # dark | light
    "board": "classic",     # board colour theme
    "pieces": "cburnett",   # piece set
    "sound": True,
    "engine": None,         # default analysis level (id from config.ENGINE_PRESETS)
    "effort": None,         # CPU effort (id from config.EFFORT_LEVELS)
}


def get_settings():
    """User preferences (linked account, theme, board...) merged over defaults."""
    settings = dict(DEFAULT_SETTINGS)
    with _connect() as conn:
        for row in conn.execute("SELECT key, value FROM settings").fetchall():
            if row["key"] in settings:
                settings[row["key"]] = json.loads(row["value"])
    return settings


def update_settings(changes):
    """Persist the known keys of ``changes`` and return the full settings."""
    with _connect() as conn:
        for key, value in changes.items():
            if key in DEFAULT_SETTINGS:
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                             (key, json.dumps(value)))
    return get_settings()

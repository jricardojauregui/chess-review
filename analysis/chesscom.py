"""Client for the public chess.com API (read-only, no auth needed)."""
import re
from datetime import datetime, timezone

import requests

import config


class ChessComError(Exception):
    """An API problem with a user-facing message and an HTTP status to relay."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


_DRAW_CODES = {"agreed", "repetition", "stalemate", "insufficient", "50move",
               "timevsinsufficient"}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_-]{2,40}$")


def _get(url, username):
    try:
        response = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                                timeout=config.HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise ChessComError(f"Could not reach chess.com ({exc.__class__.__name__}). "
                            "Check your internet connection.", 502)
    if response.status_code == 404:
        raise ChessComError(f'chess.com user "{username}" was not found.', 404)
    if response.status_code == 429:
        raise ChessComError("chess.com is rate-limiting requests right now. "
                            "Wait a minute and try again.", 429)
    if response.status_code >= 400:
        raise ChessComError(f"chess.com answered with an error ({response.status_code}).", 502)
    return response.json()


def validate_username(username):
    username = (username or "").strip()
    if not _USERNAME_RE.match(username):
        raise ChessComError("That does not look like a valid chess.com username.", 400)
    return username


def get_archives(username):
    """List of available months as "YYYY-MM", newest first."""
    data = _get(f"{config.CHESSCOM_API}/player/{username.lower()}/games/archives", username)
    months = []
    for url in data.get("archives", []):
        year, month = url.rstrip("/").split("/")[-2:]
        months.append(f"{year}-{month}")
    return sorted(months, reverse=True)


def opening_from_eco_url(url):
    """"…/openings/Sicilian-Defense-Open-2...Nc6" -> "Sicilian Defense Open"."""
    if not url:
        return None
    slug = url.rstrip("/").split("/")[-1]
    slug = re.split(r"(?:-|\.\.\.)\d+\.", slug)[0]   # cut where the move list starts
    return slug.replace("-", " ").strip(" .") or None


def _result(white_code, black_code):
    if white_code == "win":
        return "1-0"
    if black_code == "win":
        return "0-1"
    if white_code in _DRAW_CODES or black_code in _DRAW_CODES:
        return "1/2-1/2"
    return "*"


def _game_item(raw, username=None):
    """Normalise one game of the public API (keeps the PGN)."""
    white, black = raw["white"], raw["black"]
    hero = None
    if username:
        if white["username"].lower() == username.lower():
            hero = "w"
        elif black["username"].lower() == username.lower():
            hero = "b"
    result = _result(white.get("result"), black.get("result"))
    outcome = "draw" if result == "1/2-1/2" else "other"
    if hero and result in ("1-0", "0-1"):
        outcome = "win" if (result == "1-0") == (hero == "w") else "loss"
    end_time = raw.get("end_time")
    accuracies = raw.get("accuracies") or {}
    return {
        "pgn": raw["pgn"],
        "url": raw.get("url"),
        "white": {"name": white["username"], "rating": white.get("rating")},
        "black": {"name": black["username"], "rating": black.get("rating")},
        "result": result,
        "hero": hero,
        "outcome": outcome,
        "termination": (white if result == "0-1" else black).get("result"),
        "time_control": raw.get("time_control"),
        "time_class": raw.get("time_class"),
        "rated": raw.get("rated"),
        "end_time": end_time,
        "date": (datetime.fromtimestamp(end_time, tz=timezone.utc).strftime("%Y-%m-%d")
                 if end_time else None),
        "opening": opening_from_eco_url(raw.get("eco")),
        "final_fen": raw.get("fen"),                       # for the hover preview
        "cc_accuracy": ({"w": accuracies.get("white"), "b": accuracies.get("black")}
                        if accuracies else None),          # chess.com's own number
    }


def get_games(username, month):
    """Standard-chess games of one month ("YYYY-MM"), newest first.

    Each item keeps the PGN plus the fields the game list needs.
    """
    if not re.match(r"^\d{4}-\d{2}$", month or ""):
        raise ChessComError("month must look like YYYY-MM.", 400)
    year, mon = month.split("-")
    data = _get(f"{config.CHESSCOM_API}/player/{username.lower()}/games/{year}/{mon}", username)
    games = [_game_item(raw, username) for raw in data.get("games", [])
             if raw.get("rules") == "chess" and raw.get("pgn")]   # skip variants
    games.sort(key=lambda g: g["end_time"] or 0, reverse=True)
    return games


# ----------------------------------------------------------- game by id
_TCN = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!?{~}(^)[_]@#$,./&-*++="


def decode_tcn(tcn):
    """chess.com's compact move encoding -> list of UCI strings."""
    names = [f + r for r in "12345678" for f in "abcdefgh"]
    moves = []
    for i in range(0, len(tcn) - 1, 2):
        a, b = _TCN.index(tcn[i]), _TCN.index(tcn[i + 1])
        if a > 63:                                  # piece drops (variants)
            raise ValueError("unsupported move in TCN")
        promotion = ""
        if b > 63:
            promotion = "qnrbkp"[(b - 64) // 3]
            b = a + (-8 if a < 16 else 8) + (b - 1) % 3 - 1
        moves.append(names[a] + names[b] + promotion)
    return moves


def parse_game_ref(ref):
    """"187015500984" or a chess.com game URL -> (kind, id). kind: live|daily|None."""
    ref = (ref or "").strip()
    match = re.search(r"chess\.com/(?:analysis/)?game/(live|daily)/(\d+)", ref)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r"chess\.com/(live|daily)/game/(\d+)", ref)
    if match:
        return match.group(1), match.group(2)
    if re.fullmatch(r"\d{5,20}", ref):
        return None, ref
    raise ChessComError("Enter a chess.com game ID (the number at the end of the game "
                        "link) or the full game URL.", 400)


def _callback(kind, game_id):
    """chess.com's own web endpoint for one game; None when it does not exist."""
    url = f"https://www.chess.com/callback/{kind}/game/{game_id}"
    try:
        response = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                                timeout=config.HTTP_TIMEOUT)
    except requests.RequestException:
        raise ChessComError("Could not reach chess.com. Check your internet connection.", 502)
    if response.status_code == 429:
        raise ChessComError("chess.com is rate-limiting requests right now. "
                            "Wait a minute and try again.", 429)
    if response.status_code != 200:
        return None
    try:
        return response.json().get("game")
    except ValueError:
        return None


def get_game_by_id(ref, username=None):
    """Find one specific game by id or URL. Returns an item like ``get_games``.

    The public API has no "game by id" endpoint, so this asks chess.com's web
    endpoint who played and when, then looks the game up in that player's
    monthly archive (which has the full PGN with clocks). If the archive does
    not have it, the PGN is rebuilt from the encoded move list.
    """
    kind, game_id = parse_game_ref(ref)
    game = None
    for candidate in ([kind] if kind else ["live", "daily"]):
        game = _callback(candidate, game_id)
        if game:
            kind = candidate
            break
    if not game:
        raise ChessComError(f"Game {game_id} was not found on chess.com.", 404)
    headers = game.get("pgnHeaders") or {}
    white = headers.get("White")

    # 1) the player's archive: complete PGN with clock times
    end = game.get("endTime")
    months = []
    if end:
        months.append(datetime.fromtimestamp(end, tz=timezone.utc).strftime("%Y-%m"))
    date = (headers.get("Date") or "").replace(".", "-")[:7]
    if re.match(r"^\d{4}-\d{2}$", date) and date not in months:
        months.append(date)
    if white:
        for month in months:
            try:
                year, mon = month.split("-")
                data = _get(f"{config.CHESSCOM_API}/player/{white.lower()}/games/{year}/{mon}", white)
            except ChessComError:
                continue
            for raw in data.get("games", []):
                if (raw.get("url") or "").rstrip("/").endswith("/" + game_id) and raw.get("pgn"):
                    if raw.get("rules") != "chess":
                        raise ChessComError("That game is a chess variant, which is not supported.", 400)
                    return _game_item(raw, username)

    # 2) fallback: rebuild the PGN from the move list
    import chess
    import chess.pgn
    try:
        ucis = decode_tcn(game.get("moveList") or "")
    except ValueError:
        raise ChessComError("That game uses moves this app does not support.", 400)
    start = headers.get("FEN") or chess.STARTING_FEN
    board = chess.Board(start)
    pgn_game = chess.pgn.Game()
    for key in ("Event", "Site", "Date", "White", "Black", "Result", "WhiteElo", "BlackElo",
                "TimeControl", "Termination"):
        if headers.get(key) is not None:
            pgn_game.headers[key] = str(headers[key])
    pgn_game.headers["Link"] = f"https://www.chess.com/game/{kind}/{game_id}"
    if start != chess.STARTING_FEN:
        pgn_game.setup(board)
    node = pgn_game
    for uci in ucis:
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            raise ChessComError("Could not read the moves of that game.", 502)
        node = node.add_variation(move)
        board.push(move)
    if not ucis:
        raise ChessComError("That game has no moves.", 400)
    raw = {
        "pgn": str(pgn_game), "url": pgn_game.headers["Link"], "rules": "chess",
        "white": {"username": headers.get("White", "White"), "rating": headers.get("WhiteElo"),
                  "result": "win" if headers.get("Result") == "1-0" else
                            ("agreed" if headers.get("Result") == "1/2-1/2" else "lose")},
        "black": {"username": headers.get("Black", "Black"), "rating": headers.get("BlackElo"),
                  "result": "win" if headers.get("Result") == "0-1" else
                            ("agreed" if headers.get("Result") == "1/2-1/2" else "lose")},
        "time_control": headers.get("TimeControl"), "end_time": end, "fen": board.fen(),
    }
    return _game_item(raw, username)


def get_player(username):
    """Public profile (avatar, name, country...)."""
    data = _get(f"{config.CHESSCOM_API}/player/{username.lower()}", username)
    return {"username": data.get("username", username), "avatar": data.get("avatar"),
            "name": data.get("name"), "title": data.get("title"),
            "url": data.get("url")}

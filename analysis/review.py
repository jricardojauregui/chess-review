"""Glue between PGN, engine output, classification and coach.

``build_review`` turns a stored game + its cached engine analysis into the
JSON the review screen consumes (moves, summary, coach messages).
"""
import io
from functools import lru_cache

import chess
import chess.pgn

import config
from analysis import classify, coach, openings, store
from analysis.engine import line_win


class PgnError(ValueError):
    """The PGN could not be parsed or has no moves."""


def parse_pgn(pgn):
    """Return ``(game, start_board, moves, clocks)`` for the PGN main line.

    ``clocks`` holds the %clk value (seconds) after each move, or None.
    """
    try:
        game = chess.pgn.read_game(io.StringIO(pgn))
    except Exception as exc:                      # python-chess is lenient, but be safe
        raise PgnError(f"Could not read the PGN: {exc}")
    if game is None:
        raise PgnError("The PGN is empty.")
    if game.errors:
        detail = str(game.errors[0]).split(" in ")[0]
        raise PgnError(f"The PGN has an illegal or unreadable move ({detail}).")
    moves = list(game.mainline_moves())
    if not moves:
        raise PgnError("The PGN has no moves.")
    clocks = [node.clock() for node in game.mainline()]
    return game, game.board(), moves, clocks


def _rating(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def meta_from_pgn(game, username=None):
    """Game metadata from PGN headers (used for pasted PGNs)."""
    headers = game.headers
    white, black = headers.get("White", "White"), headers.get("Black", "Black")
    hero = None
    if username:
        if white.lower() == username.lower():
            hero = "w"
        elif black.lower() == username.lower():
            hero = "b"
    date = headers.get("UTCDate") or headers.get("Date") or ""
    date = date.replace(".", "-") if "?" not in date else None
    return {
        "white": {"name": white if white != "?" else "White",
                  "rating": _rating(headers.get("WhiteElo"))},
        "black": {"name": black if black != "?" else "Black",
                  "rating": _rating(headers.get("BlackElo"))},
        "result": headers.get("Result", "*"),
        "hero": hero,
        "date": date or None,
        "time_control": headers.get("TimeControl"),
        "termination": headers.get("Termination"),
        "url": headers.get("Link") or headers.get("Site"),
    }


def _phase_quality(accuracy):
    for minimum, label in config.PHASE_QUALITY:
        if accuracy >= minimum:
            return label
    return config.PHASE_QUALITY[-1][1]


def _areas(result):
    """Areas of play (config.SKILL_AREAS) a classified move counts toward."""
    if result["phase"] == "opening":
        return set()
    if config.SKILL_TACTICAL_TAGS & set(result["tags"]):
        return {"tactics"}
    return {"strategy"}


def _blend(accuracies):
    """Average of the plain and the harmonic mean: bad moves weigh more, as in the game accuracy."""
    mean = sum(accuracies) / len(accuracies)
    harmonic = len(accuracies) / sum(1 / max(a, 1.0) for a in accuracies)
    return (mean + harmonic) / 2


def _summary(results, accuracy, result, hero, lang="en", ratings=None):
    ratings = ratings or {}
    counts = {c: {label: 0 for label in classify.ALL_LABELS} for c in "wb"}
    for r in results:
        counts[r["color"]][r["cls"]] += 1
    moves = {c: [r for r in results if r["color"] == c] for c in "wb"}
    overall = {c: _blend([r["accuracy"] for r in moves[c]]) if moves[c] else None for c in "wb"}

    def part(color, chosen, minimum=1):
        """Accuracy, quality icon and estimated rating of some of a player's moves.

        The rating is the game rating moved by how much better or worse these
        moves were than the player's game as a whole, so the parts stay
        consistent with the overall number.
        """
        accs = [r["accuracy"] for r in chosen]
        if len(accs) < minimum:
            return None
        mean = sum(accs) / len(accs)
        rating = None
        if accuracy[color] is not None and len(moves[color]) >= config.GAME_RATING_MIN_MOVES:
            shifted = accuracy[color] + _blend(accs) - overall[color]
            rating = classify.game_rating(max(0.0, min(100.0, shifted)), ratings.get(color))
        return {"moves": len(accs), "accuracy": round(mean, 1), "quality": _phase_quality(mean),
                "rating": rating}

    phases = {phase: {c: part(c, [r for r in moves[c] if r["phase"] == phase]) for c in "wb"}
              for phase in ("opening", "middlegame", "endgame")}
    # Advanced stats: the same numbers for the tactical and the quiet moves
    skills = {area: {c: part(c, [r for r in moves[c] if area in _areas(r)], config.SKILL_MIN_MOVES)
                     for c in "wb"} for area in config.SKILL_AREAS}
    game_rating = {c: (classify.game_rating(accuracy[c], ratings.get(c))
                       if len(moves[c]) >= config.GAME_RATING_MIN_MOVES else None) for c in "wb"}
    return {
        "accuracy": accuracy,
        "game_rating": game_rating,          # estimated strength shown in this game
        "counts": counts,
        "phases": phases,
        "skills": skills,
        "comment": coach.summary_comment(results, counts, accuracy, result, hero, lang),
    }


def build_review(game_row, positions, depth, hero=None, lang="en"):
    """Full review payload for one game (coach texts in ``lang``: "en" | "es")."""
    game, board, moves, clocks = parse_pgn(game_row["pgn"])
    if len(positions) != len(moves) + 1:
        raise PgnError("Cached analysis does not match this game.")
    meta = dict(game_row["meta"])
    hero = hero if hero in ("w", "b") else meta.get("hero")

    book_plies, names, opening = openings.detect(board, moves)
    results = classify.classify_game(board, moves, positions, book_plies, names)
    coach.annotate(results, game_row["id"], hero, lang)
    for r, clock in zip(results, clocks):
        r["clock"] = clock

    first = positions[0]["lines"][0] if positions[0].get("lines") else None
    white_first = board.turn == chess.WHITE
    start_win = 50.0
    start_eval = {"cp": 0, "mate": None, "text": "0.00"}
    standard_start = board.fen() == chess.STARTING_FEN
    if first and not (config.START_EVAL_ZERO and standard_start):
        win = line_win(first)
        start_win = win if white_first else 100 - win
        start_eval = classify._white_eval(first["cp"], first["mate"], white_first)

    accuracy = classify.game_accuracy(results, start_win)
    return {
        "analysed": True,
        "game": {"id": game_row["id"], **meta, "opening_book": opening,
                 "moves": len(moves)},
        "depth": depth,
        "hero": hero,
        "start": {"fen": board.fen(), "win_white": round(start_win, 2), "eval": start_eval},
        "moves": results,
        "summary": _summary(results, accuracy, meta.get("result"), hero, lang,
                            {"w": (meta.get("white") or {}).get("rating"),
                             "b": (meta.get("black") or {}).get("rating")}),
        "coach_lines": coach.interactive(lang),
        "labels": classify.ALL_LABELS,
    }


def build_preview(game_row, hero=None, lang="en"):
    """The game without engine analysis: enough to show and replay the board."""
    game, board, moves, clocks = parse_pgn(game_row["pgn"])
    meta = dict(game_row["meta"])
    hero = hero if hero in ("w", "b") else meta.get("hero")
    _, _, opening = openings.detect(board, moves)
    walker = board.copy()
    plain = []
    for index, move in enumerate(moves):
        item = {"ply": index + 1, "move_number": walker.fullmove_number,
                "color": "w" if walker.turn == chess.WHITE else "b",
                "san": walker.san(move), "uci": move.uci(),
                "fen_before": walker.fen(), "cls": None, "clock": clocks[index]}
        walker.push(move)
        item["fen_after"] = walker.fen()
        plain.append(item)
    return {
        "analysed": False,
        "game": {"id": game_row["id"], **meta, "opening_book": opening, "moves": len(moves)},
        "depth": None,
        "hero": hero,
        "start": {"fen": board.fen(), "win_white": 50.0,
                  "eval": {"cp": 0, "mate": None, "text": "0.00"}},
        "moves": plain,
        "coach_lines": coach.interactive(lang),
        "labels": classify.ALL_LABELS,
    }


@lru_cache(maxsize=256)
def cached_review(game_id, depth):
    """Review with the game's default hero; memoised for stats/puzzles.

    The returned dict is shared: treat it as read-only.
    """
    row = store.get_game(game_id)
    positions = store.get_analysis(game_id, depth)
    if row is None or positions is None:
        return None
    return build_review(row, positions, depth)

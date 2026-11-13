"""Training puzzles: a bank of multi-move puzzles (data/puzzles.tsv, built by
scripts/build_puzzles.py) served in sessions that lean toward what the user
gets wrong in their own games.

The puzzles are NOT taken from the user's games. Their reviewed games only
decide the mix: somebody who keeps missing checkmates gets more mating
puzzles, somebody who leaves pieces hanging gets more loose-piece puzzles.
"""
import bisect
import random
import threading

import chess

import config
from analysis import classify as C

# What the trainer can focus on. ``themes`` are the puzzle-bank themes that
# train it; ``reason`` is filled with the number of errors found in the games.
FOCUS = [
    {"id": "mates", "label": "Finding checkmates", "themes": ["mateIn1", "mateIn2", "mateIn3"],
     "reason": "You missed a forced checkmate {n} time{s}"},
    {"id": "king", "label": "King safety and mating patterns",
     "themes": ["backRankMate", "defensiveMove", "exposedKing", "kingsideAttack"],
     "reason": "You walked into a forced checkmate {n} time{s}"},
    {"id": "loose", "label": "Loose pieces", "themes": ["hangingPiece", "trappedPiece"],
     "reason": "You left a piece hanging {n} time{s}"},
    {"id": "tactics", "label": "Forks, pins and skewers",
     "themes": ["fork", "pin", "skewer", "discoveredAttack", "deflection"],
     "reason": "You missed a winning tactic {n} time{s}"},
    {"id": "opening", "label": "Opening tactics", "themes": ["opening"],
     "reason": "{n} of your serious errors came in the opening"},
    {"id": "endgame", "label": "Endgames", "themes": ["endgame", "promotion"],
     "reason": "{n} of your serious errors came in the endgame"},
]
_FOCUS_BY_ID = {f["id"]: f for f in FOCUS}
_ERRORS = (C.MISTAKE, C.BLUNDER, C.MISS)
# error tag -> focus it feeds
_TAG_FOCUS = {"missed_mate": "mates", "allows_mate": "king", "hangs_piece": "loose",
              "missed_tactic": "tactics"}

_bank = None
_lock = threading.Lock()


def bank():
    """The puzzle bank: {"all": [puzzle], "by_theme": {theme: ([ratings], [puzzle])}}."""
    global _bank
    with _lock:
        if _bank is None:
            puzzles = []
            if config.PUZZLES_PATH.exists():
                with open(config.PUZZLES_PATH, encoding="utf-8") as handle:
                    for line in handle:
                        parts = line.rstrip("\n").split("\t")
                        if len(parts) != 5:
                            continue
                        moves = parts[2].split()
                        puzzles.append({"id": parts[0], "fen": parts[1], "lead": moves[0],
                                        "moves": moves[1:], "rating": int(parts[3]),
                                        "themes": parts[4].split()})
            puzzles.sort(key=lambda p: p["rating"])
            by_theme = {}
            for puzzle in puzzles:
                for theme in puzzle["themes"]:
                    by_theme.setdefault(theme, []).append(puzzle)
            _bank = {"all": puzzles,
                     "by_theme": {t: ([p["rating"] for p in items], items)
                                  for t, items in by_theme.items()},
                     "ratings": [p["rating"] for p in puzzles]}
        return _bank


# --------------------------------------------------------------------------
# What the user gets wrong
# --------------------------------------------------------------------------
def weaknesses(reviews):
    """Count the user's serious errors per focus, from their reviewed games.

    Returns ``{"games", "errors", "focus": [{id, label, count, share, reason}]}``
    with the focus list sorted from most to least needed. ``share`` (0..100) is
    how much of a session goes to each one.
    """
    counts = {f["id"]: 0 for f in FOCUS}
    errors = 0
    for review in reviews:
        hero = review["hero"]
        for move in review["moves"]:
            if move["color"] != hero or move["cls"] not in _ERRORS:
                continue
            errors += 1
            for tag, focus in _TAG_FOCUS.items():
                if tag in move["tags"]:
                    counts[focus] += 1
            if move["cls"] == C.MISS and "missed_mate" not in move["tags"]:
                counts["tactics"] += 1            # the opponent slipped and it went unpunished
            if move["phase"] in ("opening", "endgame"):
                counts[move["phase"]] += 1
    # every focus keeps a base share so sessions stay varied
    weights = {key: config.PUZZLE_FOCUS_BASE + n for key, n in counts.items()}
    total = sum(weights.values())
    focus = []
    for item in FOCUS:
        n = counts[item["id"]]
        focus.append({"id": item["id"], "label": item["label"], "count": n,
                      "share": round(100 * weights[item["id"]] / total),
                      "reason": item["reason"].format(n=n, s="" if n == 1 else "s") if n else None})
    focus.sort(key=lambda f: -f["count"])
    return {"games": len(reviews), "errors": errors, "focus": focus}


def start_rating(player_rating):
    """Puzzle rating to start from, given the user's game rating (may be None).

    Puzzle ratings run higher than rapid ratings, hence the offset.
    """
    if not player_rating:
        return config.PUZZLE_START_RATING
    return max(config.PUZZLE_RATING_MIN + 200,
               min(1800, int(player_rating) + config.PUZZLE_RATING_OFFSET))


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------
def _near(ratings, items, rating, seen, rng):
    """A random unseen puzzle close to ``rating`` (the window widens until one is found)."""
    window = config.PUZZLE_RATING_WINDOW
    while window <= 2000:
        lo = bisect.bisect_left(ratings, rating - window)
        hi = bisect.bisect_right(ratings, rating + window)
        pool = [p for p in items[lo:hi] if p["id"] not in seen]
        if pool:
            return rng.choice(pool)
        window *= 2
    return None


def _public(puzzle, focus_id):
    turn = puzzle["fen"].split(" ")[1]
    return {"id": puzzle["id"], "fen": puzzle["fen"], "lead": puzzle["lead"],
            "moves": puzzle["moves"], "rating": puzzle["rating"], "themes": puzzle["themes"],
            "color": "b" if turn == "w" else "w",          # the solver moves second
            "focus": focus_id}


def session(profile, rating, count=None, seen=(), rng=None):
    """``count`` shuffled puzzles around ``rating``, mixed by the weakness profile."""
    rng = rng or random.Random()
    count = max(1, min(40, count or config.PUZZLE_SESSION_SIZE))
    rating = max(config.PUZZLE_RATING_MIN, min(config.PUZZLE_RATING_MAX, int(rating)))
    data = bank()
    seen = set(seen)
    ids = [f["id"] for f in profile["focus"]]
    shares = [max(1, f["share"]) for f in profile["focus"]]
    out = []
    for _ in range(count):
        focus_id = rng.choices(ids, weights=shares)[0]
        theme = rng.choice(_FOCUS_BY_ID[focus_id]["themes"])
        ratings, items = data["by_theme"].get(theme, ([], []))
        # a little spread so a session is not all the same difficulty
        target = rating + rng.randint(-60, 60)
        puzzle = _near(ratings, items, target, seen, rng) \
            or _near(data["ratings"], data["all"], target, seen, rng)
        if puzzle is None:
            break
        seen.add(puzzle["id"])
        out.append(_public(puzzle, focus_id))
    return out


def validate(puzzle):
    """True when the puzzle's whole line is legal (used by the tests)."""
    try:
        board = chess.Board(puzzle["fen"])
        for uci in [puzzle["lead"], *puzzle["moves"]]:
            board.push_uci(uci)
    except ValueError:
        return False
    return len(puzzle["moves"]) % 2 == 1

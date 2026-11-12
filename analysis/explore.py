"""Live position analysis for the "what if?" exploration on the review board.

Keeps one Stockfish process alive between requests (starting it takes longer
than the search itself) and remembers recent positions.
"""
import threading
from collections import OrderedDict

import chess

import config
from analysis.classify import _white_eval
from analysis.engine import Engine, line_win

_engine = None
_idle_timer = None
_lock = threading.Lock()
_cache = OrderedDict()
_CACHE_SIZE = 2000


def analyse_fen(fen, depth=None):
    """Top engine lines for a position.

    Returns ``{"fen", "turn", "terminal", "win_white", "eval", "lines"}`` where
    every line carries its eval from White's point of view, the mover's win%
    and the principal variation in SAN.
    """
    global _engine
    depth = depth or config.EXPLORE_DEPTH
    board = chess.Board(fen)                 # raises ValueError on a bad FEN
    if not board.is_valid():
        raise ValueError("That position is not legal.")
    key = (board.fen(), depth)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        if _engine is None:
            _engine = Engine()
        try:
            raw = _engine.analyse_position(board, depth, multipv=config.EXPLORE_MULTIPV,
                                           max_seconds=config.EXPLORE_MAX_SECONDS)
        except Exception:
            # The process died: drop it so the next request starts a fresh one.
            _engine.close()
            _engine = None
            raise

        white = board.turn == chess.WHITE
        lines = []
        for line in raw["lines"]:
            lines.append({"uci": line["uci"], "san": line["san"], "pv": line["pv"],
                          "pv_san": line["pv_san"], "win": round(line_win(line), 2),
                          "eval": _white_eval(line["cp"], line["mate"], white)})
        if raw["terminal"] == "checkmate":
            win_white = 0.0 if white else 100.0          # side to move is mated
            evaluation = {"cp": None, "mate": 0, "text": "#"}
        elif raw["terminal"] == "draw" or not lines:
            win_white, evaluation = 50.0, {"cp": 0, "mate": None, "text": "0.00"}
        else:
            win_white = lines[0]["win"] if white else 100 - lines[0]["win"]
            evaluation = lines[0]["eval"]
        result = {"fen": board.fen(), "turn": "w" if white else "b",
                  "terminal": raw["terminal"], "win_white": round(win_white, 2),
                  "eval": evaluation, "lines": lines, "depth": depth}
        _cache[key] = result
        if len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
        _arm_idle_timer()
        return result


def _arm_idle_timer():
    """(Re)start the countdown that stops the engine when nobody is using it."""
    global _idle_timer
    if _idle_timer is not None:
        _idle_timer.cancel()
    _idle_timer = threading.Timer(config.EXPLORE_IDLE_SECONDS, shutdown)
    _idle_timer.daemon = True
    _idle_timer.start()


def is_running():
    return _engine is not None


def shutdown():
    """Stop the engine process. Must be called before the program exits:
    the engine's worker thread would otherwise keep Python from quitting."""
    global _engine, _idle_timer
    with _lock:
        if _idle_timer is not None:
            _idle_timer.cancel()
            _idle_timer = None
        if _engine is not None:
            _engine.close()
            _engine = None

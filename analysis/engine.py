"""Stockfish wrapper and eval helpers.

Every score produced here is from the point of view of the side to move in the
analysed position. The raw per-position output is plain JSON-serialisable data
so it can be cached in SQLite and classified later.
"""
import math
import os
import shutil
import threading
import time

import chess
import chess.engine

import config


class EngineNotFound(RuntimeError):
    """Raised when no Stockfish binary can be located."""


class AnalysisCancelled(RuntimeError):
    """Raised when an analysis is stopped before it finishes."""


# --------------------------------------------------------------------------
# Eval helpers
# --------------------------------------------------------------------------
def cp_to_win(cp):
    """Centipawns -> win% (0..100) for the side the score belongs to."""
    cp = max(-config.MATE_CP, min(config.MATE_CP, cp))
    return 50 + 50 * (2 / (1 + math.exp(-config.WIN_K * cp)) - 1)


def line_cp(line):
    """Centipawn value of an engine line; mates become +/- MATE_CP."""
    if line.get("mate") is not None:
        return config.MATE_CP if line["mate"] > 0 else -config.MATE_CP
    return max(-config.MATE_CP, min(config.MATE_CP, line.get("cp") or 0))


def line_win(line):
    """Win% of an engine line for the side to move."""
    return cp_to_win(line_cp(line))


# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
class Engine:
    """Thin context-managed wrapper around a Stockfish process."""

    def __init__(self, path=None, threads=None, hash_mb=None):
        path = path or config.find_stockfish()
        if not path:
            raise EngineNotFound(
                "Stockfish was not found. Install it or set STOCKFISH_PATH in .env "
                "(see README)."
            )
        self.path = path
        # Token passed to every search: while it stays the same the engine keeps
        # its hash table between positions (no "ucinewgame"), which is much faster.
        self._game = object()
        # Lower OS priority: analysis yields to whatever else the computer is doing.
        command = path
        nice = shutil.which("nice") if os.name == "posix" else None
        if config.ENGINE_NICE and nice:
            command = [nice, "-n", str(config.ENGINE_NICE), path]
        self._engine = chess.engine.SimpleEngine.popen_uci(command)
        options = {
            "Threads": threads or config.ENGINE_THREADS,
            "Hash": hash_mb or config.ENGINE_HASH_MB,
        }
        try:
            self._engine.configure(options)
        except chess.engine.EngineError:
            pass  # exotic builds without these options still work

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        try:
            self._engine.quit()
        except Exception:
            pass

    def new_game(self):
        """Forget the previous game (clears the engine's hash on next search)."""
        self._game = object()

    def analyse_position(self, board, depth=None, multipv=None, max_seconds=None):
        """Analyse one position with MultiPV.

        Returns ``{"fen", "terminal", "legal_count", "lines"}`` where each line
        is ``{"uci", "san", "cp", "mate", "pv", "pv_san"}`` from the mover's POV
        (exactly one of cp/mate is set). ``terminal`` is "checkmate", "draw" or
        None; terminal positions are not sent to the engine.
        """
        depth = depth or config.DEPTH_DEFAULT
        result = {
            "fen": board.fen(),
            "terminal": None,
            "legal_count": board.legal_moves.count(),
            "lines": [],
        }
        if board.is_checkmate():
            result["terminal"] = "checkmate"
            return result
        if board.is_stalemate() or board.is_insufficient_material():
            result["terminal"] = "draw"
            return result

        limit = chess.engine.Limit(depth=depth,
                                   time=max_seconds or config.MAX_SECONDS_PER_POSITION)
        multipv = max(1, min(multipv or config.MULTIPV, result["legal_count"]))
        infos = self._engine.analyse(board, limit, multipv=multipv, game=self._game)
        for info in infos:
            pv = info.get("pv") or []
            if not pv:
                continue
            score = info["score"].pov(board.turn)
            pv = pv[: config.PV_LENGTH]
            pv_san = []
            walker = board.copy(stack=False)
            for move in pv:
                pv_san.append(walker.san(move))
                walker.push(move)
            result["lines"].append({
                "uci": pv[0].uci(),
                "san": pv_san[0],
                "cp": score.score(),      # None when it is a mate score
                "mate": score.mate(),     # None when it is a cp score
                "pv": [m.uci() for m in pv],
                "pv_san": pv_san,
            })
        return result


def analyse_line(engine, start_board, moves, depth=None, progress=None, max_seconds=None):
    """Analyse every position of a move sequence (N moves -> N+1 positions).

    ``progress(done, total, san)`` is called after each position.
    """
    engine.new_game()
    board = start_board.copy()
    positions = []
    total = len(moves) + 1
    for index in range(total):
        positions.append(engine.analyse_position(board, depth, max_seconds=max_seconds))
        san = None
        if index < len(moves):
            san = board.san(moves[index])
            board.push(moves[index])
        if progress:
            progress(index + 1, total, san)
    return positions


def analyse_line_parallel(start_board, moves, depth=None, workers=1, progress=None,
                          max_seconds=None, cancel=None):
    """Like ``analyse_line`` but with several engines working at once.

    Each worker is its own single-threaded Stockfish process. They all take the
    next unanalysed position from a shared counter, so the load balances itself
    (middlegame positions take much longer than the opening) and every engine
    still sees positions of the same game in order, which keeps its hash useful.
    The result has the same shape and order as ``analyse_line``;
    ``progress(done, total, san)`` reports how many positions are finished.
    ``cancel`` is an optional ``threading.Event``: once set, the engines are
    closed at once and ``AnalysisCancelled`` is raised.
    """
    board = start_board.copy()
    boards, sans = [board.copy()], []
    for move in moves:
        sans.append(board.san(move))
        board.push(move)
        boards.append(board.copy())
    sans.append(None)                      # the final position has no move after it
    total = len(boards)
    workers = max(1, min(workers, total))
    positions = [None] * total
    lock = threading.Lock()
    state = {"next": 0, "done": 0, "error": None}
    engines = []
    cancelled = lambda: cancel is not None and cancel.is_set()

    def work():
        try:
            with Engine(hash_mb=config.hash_mb_for(workers)) as engine:
                with lock:
                    engines.append(engine)
                while True:
                    with lock:
                        if state["error"] or cancelled() or state["next"] >= total:
                            return
                        index = state["next"]
                        state["next"] += 1
                    result = engine.analyse_position(boards[index], depth,
                                                     max_seconds=max_seconds)
                    with lock:
                        positions[index] = result
                        state["done"] += 1
                        if progress:
                            progress(state["done"], total, sans[index])
        except Exception as exc:           # stop the other workers and report it
            with lock:
                state["error"] = state["error"] or exc

    threads = [threading.Thread(target=work, daemon=True, name=f"engine-{i}")
               for i in range(workers)]
    for thread in threads:
        thread.start()
    # Wait for the workers; a cancellation closes the engines, which makes the
    # searches in flight fail right away instead of running to their time cap.
    while any(thread.is_alive() for thread in threads):
        if cancelled():
            with lock:
                for engine in engines:
                    engine.close()
        threads[0].join(timeout=0.2) if threads[0].is_alive() else time.sleep(0.05)
    if cancelled():
        raise AnalysisCancelled("Analysis stopped.")
    if state["error"]:
        raise state["error"]
    return positions

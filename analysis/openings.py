"""Opening book built from the lichess-org/chess-openings TSV files.

Every position reached along any named line counts as "theory". The parsed
book is cached as JSON next to the TSVs because building it takes a few seconds.
"""
import csv
import json
import threading

import chess

import config

_CACHE_FILE = "book_cache.json"
_book = None
_lock = threading.Lock()


def _build(tsv_files):
    """Return {epd: [eco, name] | None}. None = on a book line but unnamed."""
    positions = {}
    for tsv in tsv_files:
        with open(tsv, newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                board = chess.Board()
                try:
                    for token in row["pgn"].split():
                        if token[0].isdigit():      # "1." move numbers
                            continue
                        board.push_san(token)
                        positions.setdefault(board.epd(), None)
                except ValueError:
                    continue                        # malformed line: skip it
                positions[board.epd()] = [row["eco"], row["name"]]
    return positions


def load_book():
    """Load (and lazily build) the opening book."""
    global _book
    with _lock:
        if _book is not None:
            return _book
        tsv_files = sorted(config.OPENINGS_DIR.glob("*.tsv"))
        cache_path = config.OPENINGS_DIR / _CACHE_FILE
        stamp = [[p.name, p.stat().st_size] for p in tsv_files]
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                if cached.get("stamp") == stamp:
                    _book = cached["positions"]
                    return _book
            except (ValueError, KeyError):
                pass
        _book = _build(tsv_files)
        try:
            cache_path.write_text(
                json.dumps({"stamp": stamp, "positions": _book}), encoding="utf-8"
            )
        except OSError:
            pass
        return _book


def detect(start_board, moves):
    """Find how long a game stays in theory.

    Returns ``(book_plies, names, opening)``: the number of leading plies that
    are book moves, the opening name known after each of those plies, and the
    final ``{"eco", "name"}`` (or None). Games from a custom position have no book.
    """
    if start_board.fen() != chess.STARTING_FEN:
        return 0, [], None
    book = load_book()
    board = start_board.copy()
    names, opening = [], None
    for move in moves:
        board.push(move)
        epd = board.epd()
        if epd not in book:
            break
        if book[epd]:
            opening = {"eco": book[epd][0], "name": book[epd][1]}
        names.append(opening["name"] if opening else None)
    return len(names), names, opening

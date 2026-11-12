"""Shared fixtures. The tests use a throw-away SQLite file, never the real cache."""
import os
import sys
import tempfile
from pathlib import Path

# Must be set before config is imported anywhere
_TMP = tempfile.mkdtemp(prefix="chess-review-tests-")
os.environ["CHESS_REVIEW_DB"] = str(Path(_TMP) / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chess  # noqa: E402
import pytest  # noqa: E402

import config  # noqa: E402
from analysis import classify  # noqa: E402
from analysis.engine import Engine, analyse_line  # noqa: E402

TEST_DEPTH = 14


@pytest.fixture(scope="session")
def engine():
    """A real Stockfish process; tests that need it are skipped without one."""
    if not config.find_stockfish():
        pytest.skip("Stockfish is not installed")
    with Engine() as eng:
        yield eng


@pytest.fixture(scope="session", autouse=True)
def _stop_explore_engine():
    """The exploration engine is kept alive between requests; stop it at the end."""
    yield
    from analysis import explore
    explore.shutdown()


@pytest.fixture
def classify_line(engine):
    """classify_line(fen, [san, ...]) -> classified moves, using the real engine."""
    def run(fen, sans, depth=TEST_DEPTH, book_plies=0):
        board = chess.Board(fen)
        walker = board.copy()
        moves = [walker.push_san(san) for san in sans]
        positions = analyse_line(engine, board, moves, depth)
        return classify.classify_game(board, moves, positions, book_plies)
    return run

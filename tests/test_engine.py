import chess
import pytest

from analysis.engine import analyse_line, cp_to_win, line_cp, line_win


def test_win_percent_formula():
    assert cp_to_win(0) == pytest.approx(50.0)
    assert cp_to_win(100) == pytest.approx(59.1, abs=0.1)
    assert cp_to_win(-100) == pytest.approx(40.9, abs=0.1)
    assert cp_to_win(10000) > 99.9
    # symmetric around 50
    assert cp_to_win(350) + cp_to_win(-350) == pytest.approx(100.0)


def test_mate_is_capped_at_10000_cp():
    assert line_cp({"cp": None, "mate": 3}) == 10000
    assert line_cp({"cp": None, "mate": -1}) == -10000
    assert line_cp({"cp": 25000, "mate": None}) == 10000
    assert line_win({"cp": None, "mate": 2}) > 99.9


def test_scores_are_from_the_movers_point_of_view(engine):
    # Black to move and a queen up: the score must be positive for Black.
    board = chess.Board("4k3/8/8/8/8/8/3q4/6K1 b - - 0 1")
    pos = engine.analyse_position(board, depth=10)
    assert line_win(pos["lines"][0]) > 80
    # Same position with White to move: negative for White.
    board.turn = chess.WHITE
    pos = engine.analyse_position(board, depth=10)
    assert line_win(pos["lines"][0]) < 20


def test_multipv_and_pv_shape(engine):
    pos = engine.analyse_position(chess.Board(), depth=10)
    assert len(pos["lines"]) == 2
    best, second = pos["lines"]
    assert best["uci"] != second["uci"]
    assert 1 <= len(best["pv"]) <= 6 and len(best["pv"]) == len(best["pv_san"])
    assert pos["legal_count"] == 20 and pos["terminal"] is None


def test_terminal_positions_skip_the_engine(engine):
    mate = chess.Board("R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1")
    assert engine.analyse_position(mate)["terminal"] == "checkmate"
    stalemate = chess.Board("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1")
    assert engine.analyse_position(stalemate)["terminal"] == "draw"


def test_analyse_line_returns_n_plus_one_positions_and_reports_progress(engine):
    board = chess.Board()
    moves = [chess.Move.from_uci(u) for u in ("e2e4", "e7e5", "g1f3")]
    seen = []
    positions = analyse_line(engine, board, moves, 8, progress=lambda d, t, s: seen.append((d, t, s)))
    assert len(positions) == 4
    assert seen[0] == (1, 4, "e4") and seen[-1] == (4, 4, None)


def test_parallel_analysis_keeps_the_order_and_shape(engine):
    from analysis.engine import analyse_line_parallel
    board = chess.Board()
    moves = [chess.Move.from_uci(u) for u in ("e2e4", "e7e5", "g1f3", "b8c6", "f1c4")]
    seen = []
    positions = analyse_line_parallel(board, moves, 8, workers=3,
                                      progress=lambda d, t, s: seen.append((d, t)))
    assert len(positions) == 6 and all(p["lines"] for p in positions)
    # every position is the one reached after that many moves, in game order
    walker = chess.Board()
    for move, position in zip(moves, positions):
        assert position["fen"] == walker.fen()
        walker.push(move)
    assert positions[-1]["fen"] == walker.fen()
    assert [d for d, _ in seen] == [1, 2, 3, 4, 5, 6] and seen[-1] == (6, 6)


def test_effort_levels_never_exceed_the_fast_cores():
    import config
    levels = config.effort_levels()
    workers = [level["workers"] for level in levels]
    assert workers[0] == 1 and workers == sorted(workers)
    assert workers[-1] <= max(1, config.performance_cores())
    assert config.effort("nonsense")["id"] == config.DEFAULT_EFFORT
    assert config.hash_mb_for(1) == config.ENGINE_HASH_MB
    assert config.hash_mb_for(64) == config.ENGINE_HASH_MIN_MB

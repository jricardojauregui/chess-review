"""Classification tests.

The first half uses real Stockfish on known positions (FEN); the second half
feeds hand-made engine output to pin down the exact thresholds.
"""
import chess
import pytest

import config
from analysis import classify as C
from analysis import coach


# ---------------------------------------------------------------- with engine
def test_brilliant_legal_queen_sacrifice(classify_line):
    # Legal's mate pattern: 5.Nxe5! leaves the queen en prise (Bxd1 Bxf7+ Ke7 Nd5#).
    fen = "rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5"
    move = classify_line(fen, ["Nxe5"], depth=16)[0]
    assert move["cls"] == C.BRILLIANT
    assert "sacrifice" in move["tags"]
    assert coach.message_for(move)["expression"] == "surprised"


def test_blunder_that_hangs_the_queen(classify_line):
    # 1.e4 e5 2.Qh5 Nc6 and now 3.Qxe5+?? simply loses the queen to Nxe5.
    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3"
    move = classify_line(fen, ["Qxe5+"])[0]
    assert move["cls"] == C.BLUNDER
    assert "hangs_piece" in move["tags"] and move["info"]["hung"] == "queen"
    assert "queen" in coach.message_for(move)["text"]


def test_missed_mate_in_one(classify_line):
    # Ra8# was mate; Kf1 keeps an extra rook but lets the mate go.
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    move = classify_line(fen, ["Kf1"])[0]
    assert "missed_mate" in move["tags"] and move["info"]["missed_mate_n"] == 1
    assert move["cls"] in (C.MISS, C.MISTAKE, C.BLUNDER)
    assert move["best"]["san"] == "Ra8#"
    assert "checkmate in 1" in coach.message_for(move)["text"] or "mate in 1" in coach.message_for(move)["text"]


def test_mate_delivered_is_best(classify_line):
    fen = "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"
    move = classify_line(fen, ["Ra8#"])[0]
    assert move["cls"] == C.BEST and "checkmate" in move["tags"]
    assert move["accuracy"] == 100 and move["eval"]["text"] == "#"


def test_great_only_move_fork(classify_line):
    # Nc7+ forks king and queen: the only move that saves the game.
    fen = "4k3/8/8/1N1q4/8/8/8/4K3 w - - 0 1"
    move = classify_line(fen, ["Nc7+"])[0]
    assert move["cls"] == C.GREAT and "only_move" in move["tags"]


def test_miss_after_opponent_blunder(classify_line):
    # Black hangs the queen with 2...Qg5??; White ignores Nxg5 and plays a3.
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    blunder, miss = classify_line(fen, ["Qg5", "a3"])
    assert blunder["cls"] == C.BLUNDER
    assert miss["cls"] == C.MISS
    assert miss["best"]["san"] == "Nxg5"
    assert "Nxg5" in coach.message_for(miss)["text"]


def test_punishing_the_blunder_is_not_a_miss(classify_line):
    fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2"
    _, punish = classify_line(fen, ["Qg5", "Nxg5"])
    assert punish["cls"] in (C.GREAT, C.BEST)
    assert punish["loss"] == 0


def test_forced_single_legal_move(classify_line):
    fen = "7k/8/8/8/8/8/6q1/7K w - - 0 1"
    move = classify_line(fen, ["Kxg2"])[0]
    assert move["cls"] == C.FORCED


def test_book_moves_come_first(classify_line):
    moves = classify_line(chess.STARTING_FEN, ["e4", "e5"], depth=8, book_plies=2)
    assert [m["cls"] for m in moves] == [C.BOOK, C.BOOK]


def test_trade_is_not_a_sacrifice_or_hang(classify_line):
    # Bxf6 gxf6-style trade: giving a bishop for a knight is not a sacrifice.
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p1B1/4P3/5N2/PPP2PPP/RN1QKB1R w KQkq - 0 1"
    move = classify_line(fen, ["Bxf6"])[0]
    assert move["cls"] != C.BRILLIANT
    assert "sacrifice" not in move["tags"] and "hangs_piece" not in move["tags"]


# ------------------------------------------------------- static helper checks
def test_see_and_hanging_pieces():
    # White queen attacked by a pawn and defended: taking it still wins 9 - 1.
    board = chess.Board("4k3/8/4p3/3Q4/4P3/8/8/4K3 b - - 0 1")
    capture = chess.Move.from_uci("e6d5")
    assert C.see_capture(board, capture) == 8
    hanging = C.hanging_pieces(board, chess.WHITE)
    assert hanging[0]["piece_type"] == chess.QUEEN and hanging[0]["gain"] == 8
    # A defended knight attacked only by a queen is not hanging.
    board = chess.Board("4k3/8/8/3q4/8/3N4/2P5/4K3 b - - 0 1")
    assert C.hanging_pieces(board, chess.WHITE) == []


def test_accuracy_formula():
    assert C.accuracy_from_loss(0) == pytest.approx(100, abs=0.01)
    assert C.accuracy_from_loss(10) == pytest.approx(103.1668 * 2.718281828 ** (-0.4354) - 3.1669)
    assert C.accuracy_from_loss(100) == 0
    assert C.accuracy_from_loss(5) > C.accuracy_from_loss(15) > C.accuracy_from_loss(40)


# ------------------------------------------------- synthetic engine output
QUIET = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"


def _pos(board, lines):
    """Fake engine output: lines = [(uci, cp, mate), ...] from the mover's POV."""
    out = []
    for uci, cp, mate in lines:
        out.append({"uci": uci, "san": board.san(chess.Move.from_uci(uci)),
                    "cp": cp, "mate": mate, "pv": [uci], "pv_san": ["?"]})
    return {"fen": board.fen(), "terminal": None,
            "legal_count": board.legal_moves.count(), "lines": out}


def _single(played, best_cp, reply_cp, second_cp=None, best="g1f3", best_mate=None):
    """White plays ``played`` from QUIET; Black's best reply is worth reply_cp for Black."""
    board = chess.Board(QUIET)
    lines = [(best, best_cp, best_mate)]
    if second_cp is not None:
        lines.append(("b1c3" if best != "b1c3" else "d2d4", second_cp, None))
    before = _pos(board, lines)
    move = chess.Move.from_uci(played)
    after_board = board.copy()
    after_board.push(move)
    after = _pos(after_board, [("g8f6", reply_cp, None)])
    return C.classify_game(board, [move], [before, after])[0]


@pytest.mark.parametrize("reply_cp, expected", [
    (11, C.EXCELLENT),     # loss ~1
    (38, C.GOOD),          # loss ~3.5
    (77, C.INACCURACY),    # loss ~7
    (168, C.MISTAKE),      # loss ~15
    (377, C.BLUNDER),      # loss ~30
])
def test_loss_ladder(reply_cp, expected):
    move = _single("a2a3", best_cp=0, reply_cp=reply_cp, second_cp=-5)
    assert move["cls"] == expected
    assert move["loss"] == pytest.approx({11: 1.0, 38: 3.5, 77: 7.0, 168: 15.0, 377: 30.0}[reply_cp], abs=0.3)


def test_best_when_it_matches_the_engine():
    move = _single("g1f3", best_cp=30, reply_cp=-25, second_cp=20)
    assert move["cls"] == C.BEST and move["loss"] == 0 and move["accuracy"] == 100


def test_great_when_second_best_is_much_worse():
    move = _single("g1f3", best_cp=50, reply_cp=-50, second_cp=-250)
    assert move["cls"] == C.GREAT and "only_move" in move["tags"]


def test_not_great_when_gap_is_below_threshold():
    move = _single("g1f3", best_cp=50, reply_cp=-50, second_cp=0)   # gap ~4.6
    assert move["cls"] == C.BEST


def test_missed_mate_counts_as_miss_even_when_still_winning():
    # Mate in 2 available; the move played keeps +9 but no mate.
    move = _single("a2a3", best_cp=None, best_mate=2, reply_cp=-900, second_cp=900)
    assert move["cls"] == C.MISS and "missed_mate" in move["tags"]
    assert "2" in coach.message_for(move)["text"]


def test_thresholds_come_from_config(monkeypatch):
    monkeypatch.setattr(config, "INACCURACY_MAX", 6.0)
    move = _single("a2a3", best_cp=0, reply_cp=77, second_cp=-5)   # loss ~7
    assert move["cls"] == C.MISTAKE


def test_game_accuracy_weights_and_bounds():
    board = chess.Board(QUIET)
    results = [
        {"color": "w", "accuracy": 100.0, "win_white": 55.0},
        {"color": "b", "accuracy": 40.0, "win_white": 80.0},
        {"color": "w", "accuracy": 90.0, "win_white": 78.0},
        {"color": "b", "accuracy": 95.0, "win_white": 77.0},
    ]
    acc = C.game_accuracy(results, 52.0)
    assert 90 <= acc["w"] <= 100
    assert 40 <= acc["b"] < 80
    assert C.game_accuracy([]) == {"w": None, "b": None}
    assert board.is_valid()


def test_discovered_attack_is_not_a_sacrifice():
    # ...Nd4 can be taken (cxd4), but that uncovers Qd7xa4: a tactic, not a sacrifice.
    board = chess.Board("1r3rk1/pppq2pp/2npbn2/4pp2/Q1P2P2/2PP2P1/P3PNBP/1RB2RK1 b - - 8 12")
    assert not C.is_sacrifice(board, board.parse_san("Nd4"), [])
    # Legal's Nxe5 really does give up the queen.
    board = chess.Board("rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5")
    assert C.is_sacrifice(board, board.parse_san("Nxe5"), [])


# -------------------------------------------------- Great (chess.com style)
def test_great_requires_a_change_of_outcome():
    # Both moves still win easily: finding the better one is not "great".
    move = _single("g1f3", best_cp=900, reply_cp=-900, second_cp=450)
    assert move["cls"] == C.BEST
    # The best move is still losing: not great either.
    move = _single("g1f3", best_cp=-350, reply_cp=350, second_cp=-900)
    assert move["cls"] == C.BEST
    # Equal with the best move, lost with anything else: great.
    move = _single("g1f3", best_cp=0, reply_cp=0, second_cp=-400)
    assert move["cls"] == C.GREAT


def test_simple_retreat_of_an_attacked_piece_is_not_great(classify_line):
    # The knight on d4 is attacked by a pawn; stepping back is forced, not great.
    fen = "1r3rk1/pppq2pp/3pbn2/4pp2/2Pn1P2/2PP2P1/P3PNBP/1RBQ1RK1 b - - 10 13"
    move = classify_line(fen, ["Nc6"])[0]
    assert move["cls"] != C.GREAT


def test_start_position_reads_zero():
    from analysis import review, store
    store.init()
    pgn = "1. e4 e5 *"
    game, board, moves, _ = review.parse_pgn(pgn)
    gid = store.save_game(pgn, review.meta_from_pgn(game))
    positions = [_pos(board, [("e2e4", 35, None)])]
    walker = board.copy()
    for move, reply in zip(moves, ["e7e5", "g1f3"]):
        walker.push(move)
        positions.append(_pos(walker, [(reply, 30, None)]))
    data = review.build_review(store.get_game(gid), positions, 12)
    assert data["start"]["eval"]["text"] == "0.00" and data["start"]["win_white"] == 50


# ------------------------------------------------------------ idea arrows
def test_idea_arrows_show_what_the_move_threatens():
    # Nc7+ forks king and rook: one arrow to each target.
    board = chess.Board("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1")
    move = board.parse_san("Nc7+")
    after = board.copy()
    after.push(move)
    ideas = C.move_ideas(after, move)
    assert {(i["orig"], i["dest"], i["kind"]) for i in ideas} == {("c7", "e8", "check"), ("c7", "a8", "threat")}


def test_quiet_moves_have_no_idea_arrows():
    board = chess.Board()
    move = board.parse_san("Nf3")
    after = board.copy()
    after.push(move)
    assert C.move_ideas(after, move) == []


def test_opponent_capture_reply_is_reported(classify_line):
    # After 1.e4 d5 the natural reply is exd5: a concrete response (blue arrow).
    moves = classify_line(chess.STARTING_FEN, ["e4", "d5"], depth=10)
    assert moves[1]["reply"] == "e4d5" and moves[0]["reply"] is None


def test_bad_moves_carry_the_punishing_reply(classify_line):
    fen = "r1bqkbnr/pppp1ppp/2n5/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR w KQkq - 2 3"
    move = classify_line(fen, ["Qxe5+"])[0]
    assert move["cls"] == C.BLUNDER and move["punish"] == "c6e5"
    best = classify_line(fen, [move["best"]["san"]])[0]      # the engine's own choice
    assert best["cls"] not in (C.MISTAKE, C.BLUNDER) and best["punish"] is None

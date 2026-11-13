import chess

from analysis import classify as C
from analysis import coach, openings


def _moves(sans):
    board = chess.Board()
    return [board.push_san(s) for s in sans]


def test_book_detects_named_opening():
    moves = _moves(["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6", "Nc3", "a6"])
    plies, names, opening = openings.detect(chess.Board(), moves)
    assert plies == 10
    assert "Najdorf" in opening["name"] and opening["eco"].startswith("B9")
    assert names[0] is not None and "Sicilian" in names[1]


def test_book_stops_at_first_unknown_position():
    moves = _moves(["e4", "e5", "Ke2", "Ke7", "Ke1", "Ke8", "h4", "h5", "Rh3", "Rh6"])
    plies, names, _ = openings.detect(chess.Board(), moves)
    assert 2 <= plies < 10 and len(names) == plies


def test_no_book_from_custom_position():
    board = chess.Board("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    assert openings.detect(board, [chess.Move.from_uci("e2e4")]) == (0, [], None)


def _result(cls, tags=(), **info):
    return {"cls": cls, "tags": list(tags), "san": "Nf5", "color": "w",
            "best": {"san": "Qd2"}, "info": {"piece": "knight", **info}}


def test_every_classification_has_enough_variants_and_formats():
    values = dict(move="Nf5", best="Qd2", piece="knight", captured="pawn", material="a piece",
                  n=2, opening="Sicilian Defense", Subj="You", subj="you", poss="your",
                  Opp="Your opponent", opp="your opponent", opp_poss="your opponent's")
    seen = set()
    for (cls, context), variants in coach.TEMPLATES.items():
        assert 4 <= len(variants) <= 6, (cls, context)
        assert len(set(variants)) == len(variants)
        for template in variants:
            template.format(**values)          # raises on unknown placeholders
        seen.add(cls)
    assert seen == set(C.ALL_LABELS)
    assert set(coach.TITLES) == set(C.ALL_LABELS) == set(coach.EXPRESSIONS)


def test_titles_and_expressions():
    assert coach.message_for(_result(C.BRILLIANT))["title"] == "Nf5 is brilliant"
    assert coach.message_for(_result(C.BLUNDER))["title"] == "Nf5 is a blunder"
    assert coach.message_for(_result(C.BLUNDER))["expression"] == "sad"
    assert coach.message_for(_result(C.BEST))["expression"] == "happy"
    assert coach.message_for(_result(C.INACCURACY))["expression"] == "thinking"


def test_context_picks_specific_templates():
    hang = coach.message_for(_result(C.BLUNDER, ["hangs_piece"], hung="queen"), hero="w")
    assert "queen" in hang["text"]
    mate = coach.message_for(_result(C.MISS, ["missed_mate"], missed_mate_n=3))
    assert "3" in mate["text"] and "Qd2" in mate["text"]
    book = coach.message_for(_result(C.BOOK, opening="Italian Game"))
    assert "Italian Game" in book["text"]


def test_voice_depends_on_who_moved():
    result = _result(C.GREAT, ["refutes"])
    texts = set()
    for seed in range(5):
        texts.add(coach.message_for(result, hero="b", seed=seed)["text"])
    joined = " ".join(texts)
    assert "White" not in joined            # hero known -> you / your opponent
    neutral = " ".join(coach.message_for(result, hero=None, seed=s)["text"] for s in range(5))
    assert "You " not in neutral and "your" not in neutral


def test_variants_rotate_instead_of_repeating():
    used, texts = {}, []
    for _ in range(4):
        texts.append(coach.message_for(_result(C.BEST), seed=1, used=used)["text"])
    assert len(set(texts)) == 4


def test_summary_comment_mentions_the_decisive_blunder():
    counts = {c: {label: 0 for label in C.ALL_LABELS} for c in "wb"}
    counts["w"][C.GREAT] = 2
    counts["w"][C.BLUNDER] = 1
    comment = coach.summary_comment([{}] * 60, counts, {"w": 80.0, "b": 88.0}, "0-1", hero="w")
    assert "two great moves" in comment["text"] and "one blunder decided it" in comment["text"]
    assert comment["expression"] == "worried"

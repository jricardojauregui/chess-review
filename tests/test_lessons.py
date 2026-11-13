"""The opening lessons: every line must be legal chess and match its signature."""
import chess
import pytest

from analysis import lessons
from analysis.lessons_data import LESSONS


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_every_lesson_line_is_legal_and_commented():
    assert len({l["id"] for l in LESSONS}) == len(LESSONS) >= 36
    for lesson in LESSONS:
        lines = lessons._lines(lesson)                 # raises on an illegal move
        assert len(lines) == 1 + len(lesson.get("variations", []))
        main = [p["san"] for p in lines[0]["plies"]]
        assert any(tuple(main[: len(sig.split())]) == tuple(sig.split()) for sig in lesson["sigs"]), lesson["id"]
        assert lesson["side"] in ("w", "b") and lesson["family"] in lessons.FAMILY_NAMES
        assert lesson["why"] and lesson["watch"] and len(lesson["ideas"]) >= 3
        for line in lines:
            assert len(line["plies"]) >= 4
            assert all(p["comment"] and p["fen"] and p["uci"] for p in line["plies"])
        for variation in lesson.get("variations", []):
            assert 0 < variation["start"] <= len(lesson["line"])
        for sig in lesson["sigs"]:                     # signatures are legal too
            board = chess.Board()
            for san in sig.split():
                board.push_san(san)


def test_explainer_talks_about_what_the_move_does():
    board = chess.Board()
    assert "centre" in lessons.explain_move(board, board.parse_san("e4"))
    for san in ("e4", "e5", "Nf3", "Nc6"):
        board.push_san(san)
    assert "f7" in lessons.explain_move(board, board.parse_san("Bc4"))
    assert "Pins the knight on c6" not in lessons.explain_move(board, board.parse_san("Bb5"))  # no queen/king behind it yet
    for san in ("Bc4", "Nf6", "d3", "d6"):
        board.push_san(san)
    assert "Pins the knight on f6 to the queen" in lessons.explain_move(board, board.parse_san("Bg5"))
    assert "Castles" in lessons.explain_move(board, board.parse_san("O-O"))


def test_database_search_and_detail():
    found = lessons.search("italian evans")
    assert found and all("Evans" in f["name"] for f in found)
    assert lessons.search("") == []
    detail = lessons.lesson_detail(found[0]["id"])
    assert detail["curated"] is False and detail["parent"]["id"] == "evans-gambit"   # the most specific lesson
    assert all(p["comment"] for p in detail["lines"][0]["plies"])
    assert lessons.lesson_detail("db-99999999") is None and lessons.lesson_detail("nope") is None


def test_overview_matches_the_users_games(client):
    pgn = ('[Event "L"]\n[White "zoe"]\n[Black "yan"]\n[Result "1-0"]\n\n'
           "1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 7. Qf3+ Ke6 1-0")
    client.post("/api/games/import", json={"pgn": pgn, "username": "zoe"})
    data = lessons.overview("zoe")
    cards = {c["id"]: c for c in data["lessons"]}
    assert cards["italian"]["plays"]["games"] == 1 and cards["italian"]["plays"]["win"] == 1
    assert cards["fried-liver"]["plays"]["games"] == 1
    assert cards["two-knights"]["faces"]["games"] == 1 and cards["two-knights"]["plays"]["games"] == 0
    assert cards["sicilian"]["plays"]["games"] == 0
    assert any("played it once as White" in r for r in cards["italian"]["reasons"])
    detail = lessons.lesson_detail("fried-liver", "zoe")
    assert detail["curated"] and detail["recent"]["plays"][0]["opponent"] == "yan"
    assert len(detail["lines"]) == 2 and detail["named"]
    assert client.get("/openings").status_code == 200
    assert client.get("/api/openings").status_code == 200
    assert client.get("/api/openings/lesson/italian").get_json()["name"] == "Italian Game"
    assert client.get("/api/openings/lesson/unknown").status_code == 404
    assert client.get("/api/openings/search?q=sicilian+dragon").get_json()["results"]


def test_spanish_lessons_cover_every_line():
    """lessons_es.py mirrors the lessons: same shape, and the moves never change."""
    from analysis.lessons_es import LESSONS_ES
    assert set(LESSONS_ES) == {l["id"] for l in LESSONS}
    spanish = lessons._lessons("es")
    for lesson in LESSONS:
        es = spanish[lesson["id"]]
        assert es["name_en"] == lesson["name"] and es["why"] != lesson["why"]
        assert len(es["ideas"]) == len(lesson["ideas"]) and len(es["tags"]) == len(lesson["tags"])
        english, translated = lessons._lines(lesson), lessons._lines(es)
        assert len(english) == len(translated)
        for a, b in zip(english, translated):
            assert [p["san"] for p in a["plies"]] == [p["san"] for p in b["plies"]]
            assert all(p["comment"] for p in b["plies"])
    detail = lessons.lesson_detail("italian", lang="es")
    assert detail["name"] != "Italian Game" and detail["name_en"] == "Italian Game"
    board = chess.Board()
    assert "centro" in lessons.explain_move(board, board.parse_san("e4"), "es")
    db = lessons.lesson_detail(lessons.search("italian evans")[0]["id"], lang="es")
    assert all(p["comment"] for p in db["lines"][0]["plies"])

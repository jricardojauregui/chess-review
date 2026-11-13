"""Training puzzles: the bank, the weakness profile and the sessions."""
import random

import pytest

import config
from analysis import classify as C
from analysis import puzzles


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def _review(*moves):
    """A minimal reviewed game where the hero (White) played ``moves``: (cls, tags, phase)."""
    return {"hero": "w", "moves": [{"color": "w", "cls": cls, "tags": tags, "phase": phase}
                                   for cls, tags, phase in moves]}


def test_bank_is_large_legal_and_multi_move():
    bank = puzzles.bank()["all"]
    assert len(bank) >= 5000 and len({p["id"] for p in bank}) == len(bank)
    assert all(puzzles.validate(p) for p in bank)                  # every line can be played
    assert sum(len(p["moves"]) > 1 for p in bank) > len(bank) / 2   # most need several moves
    assert all(config.PUZZLE_RATING_MIN <= p["rating"] <= config.PUZZLE_RATING_MAX for p in bank)
    for focus in puzzles.FOCUS:                                    # every focus has material
        assert all(theme in puzzles.bank()["by_theme"] for theme in focus["themes"]), focus["id"]


def test_weaknesses_follow_the_errors():
    even = puzzles.weaknesses([])
    assert even["errors"] == 0 and len({f["share"] for f in even["focus"]}) == 1
    reviews = [_review((C.BLUNDER, ["hangs_piece"], "middlegame"),
                       (C.MISS, ["missed_mate"], "middlegame"),
                       (C.MISS, ["missed_mate"], "endgame"),
                       (C.BLUNDER, ["missed_mate", "allows_mate"], "middlegame"),
                       (C.BEST, ["missed_mate"], "middlegame"))]      # not an error: ignored
    profile = puzzles.weaknesses(reviews)
    counts = {f["id"]: f["count"] for f in profile["focus"]}
    assert profile["errors"] == 4
    assert counts == {"mates": 3, "king": 1, "loose": 1, "tactics": 0, "opening": 0, "endgame": 1}
    assert profile["focus"][0]["id"] == "mates" and "3 times" in profile["focus"][0]["reason"]
    assert profile["focus"][0]["share"] > profile["focus"][-1]["share"] > 0


def test_session_is_near_the_rating_unseen_and_weighted():
    rng = random.Random(7)
    profile = puzzles.weaknesses([_review(*[(C.MISS, ["missed_mate"], "middlegame")] * 60)])
    first = puzzles.session(profile, 900, 30, rng=rng)
    assert len(first) == 30 and len({p["id"] for p in first}) == 30
    assert all(abs(p["rating"] - 900) <= 300 for p in first)
    assert sum(p["focus"] == "mates" for p in first) > 15           # leans on the weakness
    for p in first:
        assert p["color"] != p["fen"].split(" ")[1] and len(p["moves"]) % 2 == 1
    again = puzzles.session(profile, 900, 30, seen=[p["id"] for p in first], rng=rng)
    assert not {p["id"] for p in again} & {p["id"] for p in first}
    assert puzzles.start_rating(None) == config.PUZZLE_START_RATING
    assert puzzles.start_rating(500) == 500 + config.PUZZLE_RATING_OFFSET


def test_train_api(client):
    data = client.post("/api/puzzles/train", json={"rating": 1200, "n": 5}).get_json()
    assert data["rating"] == 1200 and len(data["puzzles"]) == 5
    assert data["bank_size"] >= 5000 and len(data["profile"]["focus"]) == len(puzzles.FOCUS)
    fresh = client.post("/api/puzzles/train", json={}).get_json()    # no rating: start level
    assert fresh["rating"] >= config.PUZZLE_RATING_MIN and fresh["puzzles"]

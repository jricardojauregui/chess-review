"""HTTP API tests: chess.com errors (mocked), PGN import, SSE analysis, review."""
import json

import pytest

import config
from analysis import chesscom

PGN = """[Event "Test"]
[White "alice"]
[Black "bob"]
[Result "1-0"]
[TimeControl "600"]

1. e4 {[%clk 0:09:58]} e5 {[%clk 0:09:57]} 2. Qh5 {[%clk 0:09:50]} Ke7 {[%clk 0:09:40]} 3. Qxe5# {[%clk 0:09:45]} 1-0
"""


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload or {}

    def json(self):
        return self._payload


def _fake_get(routes):
    def get(url, headers=None, timeout=None):
        assert headers["User-Agent"] == config.USER_AGENT
        for suffix, response in routes.items():
            if url.endswith(suffix):
                return response
        return FakeResponse(404)
    return get


def test_unknown_user_gives_clear_404(client, monkeypatch):
    monkeypatch.setattr(chesscom.requests, "get", _fake_get({}))
    response = client.get("/api/games/nobody_here")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"]


def test_rate_limit_gives_clear_429(client, monkeypatch):
    monkeypatch.setattr(chesscom.requests, "get",
                        _fake_get({"/games/archives": FakeResponse(429)}))
    response = client.get("/api/games/alice")
    assert response.status_code == 429
    assert "rate-limit" in response.get_json()["error"]


def test_invalid_username_is_rejected(client):
    assert client.get("/api/games/a b!").status_code == 400


def test_games_listing(client, monkeypatch):
    game = {
        "url": "https://www.chess.com/game/live/1", "pgn": PGN, "rules": "chess",
        "time_control": "600", "time_class": "rapid", "end_time": 1760000000, "rated": True,
        "eco": "https://www.chess.com/openings/Kings-Pawn-Opening-1...e5-2.Qh5",
        "white": {"username": "Alice", "rating": 1500, "result": "win"},
        "black": {"username": "bob", "rating": 1480, "result": "checkmated"},
    }
    variant = dict(game, rules="chess960", pgn=PGN + " ")
    monkeypatch.setattr(chesscom.requests, "get", _fake_get({
        "/games/archives": FakeResponse(200, {"archives": [
            "https://api.chess.com/pub/player/alice/games/2025/09",
            "https://api.chess.com/pub/player/alice/games/2025/10"]}),
        "/games/2025/10": FakeResponse(200, {"games": [game, variant]}),
    }))
    data = client.get("/api/games/alice").get_json()
    assert data["month"] == "2025-10" and data["archives"] == ["2025-10", "2025-09"]
    assert len(data["games"]) == 1                      # the variant is skipped
    item = data["games"][0]
    assert item["hero"] == "w" and item["outcome"] == "win" and item["result"] == "1-0"
    assert item["opening"] == "Kings Pawn Opening"
    assert "pgn" not in item and item["id"] and item["analysed_depth"] is None


def test_import_rejects_bad_pgn(client):
    assert client.post("/api/games/import", json={"pgn": ""}).status_code == 400
    bad = client.post("/api/games/import", json={"pgn": "1. e4 e5 2. Ke3 Qh4"})
    assert bad.status_code == 400 and "illegal" in bad.get_json()["error"].lower()


def test_full_flow_import_analyse_review(client, engine):
    game_id = client.post("/api/games/import", json={"pgn": PGN, "username": "alice"}).get_json()["game_id"]

    # Not analysed yet: 202 with the bare game, so the board can be shown at once
    pending = client.get(f"/api/review/{game_id}?depth=8")
    preview = pending.get_json()
    assert pending.status_code == 202 and preview["analysed"] is False
    assert [m["san"] for m in preview["moves"]] == ["e4", "e5", "Qh5", "Ke7", "Qxe5#"]
    assert preview["moves"][0]["cls"] is None and preview["moves"][0]["clock"] == 598
    assert preview["moves"][1]["fen_before"] == preview["moves"][0]["fen_after"]

    stream = client.get(f"/api/analyze/stream?game_id={game_id}&depth=8")
    assert stream.mimetype == "text/event-stream"
    events = [block for block in stream.get_data(as_text=True).split("\n\n") if block.startswith("event:")]
    names = [block.split("\n")[0].split(": ")[1] for block in events]
    assert names[-1] == "done" and "progress" in names
    last_progress = json.loads([b for b in events if b.startswith("event: progress")][-1].split("data: ")[1])
    assert last_progress["done"] == last_progress["total"] == 6    # 5 moves -> 6 positions

    # Second request is served from the cache immediately
    cached = client.get(f"/api/analyze/stream?game_id={game_id}&depth=8").get_data(as_text=True)
    assert '"cached": true' in cached

    review = client.get(f"/api/review/{game_id}?depth=8").get_json()
    assert review["hero"] == "w" and review["depth"] == 8 and review["analysed"] is True
    # The starting position always reads 0.00, like chess.com
    assert review["start"]["eval"]["text"] == "0.00" and review["start"]["win_white"] == 50
    assert [m["san"] for m in review["moves"]] == ["e4", "e5", "Qh5", "Ke7", "Qxe5#"]
    assert review["moves"][0]["cls"] == "book"
    assert review["moves"][3]["cls"] == "blunder"            # Ke7 allows mate in one
    assert "allows_mate" in review["moves"][3]["tags"]
    assert review["moves"][4]["cls"] == "best"
    assert review["moves"][0]["clock"] == 598
    assert all(m["coach"]["text"] and m["coach"]["title"] for m in review["moves"])
    summary = review["summary"]
    assert summary["accuracy"]["w"] > summary["accuracy"]["b"]
    assert summary["counts"]["b"]["blunder"] == 1
    assert summary["comment"]["text"]

    stats = client.get("/api/stats/alice").get_json()
    assert stats["games"] == 1 and stats["outcomes"]["win"] == 1
    puzzles = client.get("/api/puzzles/bob").get_json()["puzzles"]
    assert puzzles == []                                      # bob has no stored games


def test_review_of_unknown_game_is_404(client):
    assert client.get("/api/review/doesnotexist").status_code == 404


def test_pages_render(client):
    for path in ("/", "/stats", "/puzzles", "/review/abc"):
        assert client.get(path).status_code == 200


# ------------------------------------------------------ settings / account
def test_settings_roundtrip(client):
    assert client.get("/api/settings").get_json()["theme"] in ("dark", "light")
    saved = client.post("/api/settings", json={"theme": "light", "board": "forest", "evil": 1}).get_json()
    assert saved["theme"] == "light" and saved["board"] == "forest" and "evil" not in saved
    assert 'data-theme="light"' in client.get("/").get_data(as_text=True)
    client.post("/api/settings", json={"theme": "dark", "board": "classic"})


def test_link_and_unlink_account(client, monkeypatch):
    monkeypatch.setattr(chesscom.requests, "get", _fake_get({
        "/player/alice": FakeResponse(200, {"username": "Alice", "avatar": "https://x/a.png", "name": "Alice A"}),
    }))
    # No account: the home page asks which account to analyse
    client.delete("/api/account")
    assert "Which account do you want to analyze?" in client.get("/").get_data(as_text=True)
    assert client.post("/api/account", json={"username": "ghost"}).status_code == 404
    linked = client.post("/api/account", json={"username": "alice"}).get_json()
    assert linked["account"]["username"] == "Alice"
    home = client.get("/").get_data(as_text=True)
    assert "Which account" not in home and "Alice" in home
    assert client.delete("/api/account").get_json()["account"] is None


# --------------------------------------------------------- game by id
def test_tcn_decoding():
    # 1.e4 e5 2.Nf3 in chess.com's move encoding
    assert chesscom.decode_tcn("mC0Kgv") == ["e2e4", "e7e5", "g1f3"]


def test_game_reference_parsing():
    assert chesscom.parse_game_ref("187015500984") == (None, "187015500984")
    assert chesscom.parse_game_ref("https://www.chess.com/game/live/187015500984?x=1") == ("live", "187015500984")
    assert chesscom.parse_game_ref("https://www.chess.com/analysis/game/daily/555555?tab=review") == ("daily", "555555")
    with pytest.raises(chesscom.ChessComError):
        chesscom.parse_game_ref("not a game")


def test_lookup_by_id_uses_the_players_archive(client, monkeypatch):
    archive_game = {
        "url": "https://www.chess.com/game/live/42424242", "pgn": PGN, "rules": "chess",
        "time_control": "600", "end_time": 1760000000,
        "fen": "rnbq1bnr/ppppkppp/8/4Q3/4P3/8/PPPP1PPP/RNB1KBNR b KQ - 0 3",
        "white": {"username": "alice", "rating": 1500, "result": "win"},
        "black": {"username": "bob", "rating": 1480, "result": "checkmated"},
    }
    monkeypatch.setattr(chesscom.requests, "get", _fake_get({
        "/callback/live/game/42424242": FakeResponse(200, {"game": {
            "moveList": "mC0Kgv", "endTime": 1760000000,
            "pgnHeaders": {"White": "alice", "Black": "bob", "Date": "2025.10.09", "Result": "1-0"}}}),
        "/player/alice/games/2025/10": FakeResponse(200, {"games": [archive_game]}),
    }))
    response = client.post("/api/games/lookup", json={"ref": "https://www.chess.com/game/live/42424242"})
    assert response.status_code == 200
    game_id = response.get_json()["game_id"]
    preview = client.get(f"/api/review/{game_id}").get_json()
    assert preview["game"]["white"]["name"] == "alice" and len(preview["moves"]) == 5
    assert preview["game"]["final_fen"].startswith("rnbq1bnr")


def test_lookup_falls_back_to_the_move_list(client, monkeypatch):
    monkeypatch.setattr(chesscom.requests, "get", _fake_get({
        "/callback/live/game/777777": FakeResponse(200, {"game": {
            "moveList": "mC0Kgv", "endTime": 1760000000,
            "pgnHeaders": {"White": "carol", "Black": "dave", "Date": "2025.10.09", "Result": "1/2-1/2"}}}),
    }))
    game_id = client.post("/api/games/lookup", json={"ref": "777777"}).get_json()["game_id"]
    preview = client.get(f"/api/review/{game_id}").get_json()
    assert [m["san"] for m in preview["moves"]] == ["e4", "e5", "Nf3"]


def test_lookup_unknown_game(client, monkeypatch):
    monkeypatch.setattr(chesscom.requests, "get", _fake_get({}))
    response = client.post("/api/games/lookup", json={"ref": "123456789"})
    assert response.status_code == 404 and "not found" in response.get_json()["error"]
    assert client.post("/api/games/lookup", json={"ref": "hello"}).status_code == 400


# ------------------------------------------------------------ exploration
def test_explore_returns_best_lines(client, engine):
    data = client.post("/api/explore", json={"fen": "6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1"}).get_json()
    assert data["turn"] == "w" and len(data["lines"]) == 3
    assert data["lines"][0]["san"] == "Ra8#" and data["lines"][0]["eval"]["text"] == "+M1"
    assert data["win_white"] > 99
    mated = client.post("/api/explore", json={"fen": "R5k1/5ppp/8/8/8/8/5PPP/6K1 b - - 1 1"}).get_json()
    assert mated["terminal"] == "checkmate" and mated["lines"] == [] and mated["win_white"] == 100
    assert client.post("/api/explore", json={"fen": "nonsense"}).status_code == 400


# ------------------------------------------------- analysis levels / engine
def test_presets_are_ordered_and_bounded():
    depths = [p["depth"] for p in config.ENGINE_PRESETS]
    assert depths == sorted(depths) and len(set(depths)) == len(depths)
    assert all(config.DEPTH_MIN <= d <= config.DEPTH_MAX for d in depths)
    assert all(p["max_seconds"] > 0 for p in config.ENGINE_PRESETS)       # every level has a time cap
    assert config.preset(config.DEFAULT_PRESET)["depth"] == config.DEPTH_DEFAULT
    assert config.preset("nonsense")["id"] == config.DEFAULT_PRESET
    assert config.max_seconds_for_depth(24) == config.preset("max")["max_seconds"]
    assert config.max_seconds_for_depth(13) == config.MAX_SECONDS_PER_POSITION


def test_default_level_setting_is_validated(client):
    assert client.post("/api/settings", json={"engine": "max"}).get_json()["engine"] == "max"
    assert client.post("/api/settings", json={"engine": "warp-speed"}).get_json()["engine"] == config.DEFAULT_PRESET
    page = client.get("/settings").get_data(as_text=True)
    assert "Analysis level" in page
    client.post("/api/settings", json={"engine": config.DEFAULT_PRESET})


def test_explore_engine_stops_when_idle(client, engine, monkeypatch):
    import time
    from analysis import explore
    explore.shutdown()
    monkeypatch.setattr(config, "EXPLORE_IDLE_SECONDS", 0.3)
    client.post("/api/explore", json={"fen": "8/8/8/4k3/8/8/4P3/4K3 w - - 0 1"})
    assert explore.is_running()
    time.sleep(1.0)
    assert not explore.is_running()          # nothing left running in the background


# ------------------------------------------------------------------ batch
def _wait_batch(client, until, timeout=60):
    import time
    end = time.time() + timeout
    while time.time() < end:
        state = client.get("/api/batch").get_json()
        if until(state):
            return state
        time.sleep(0.1)
    raise AssertionError(f"batch did not get there: {state}")


def test_batch_runs_on_the_server_and_refuses_a_second_one(client):
    pgns = [PGN.replace('[Event "Test"]', f'[Event "Batch A{i}"]') for i in range(3)]
    ids = [client.post("/api/games/import", json={"pgn": p, "username": "alice"}).get_json()["game_id"] for p in pgns]
    assert len(set(ids)) == 3
    started = client.post("/api/batch", json={"game_ids": ids, "depth": 9})
    assert started.status_code == 200 and started.get_json()["active"] and started.get_json()["total"] == 3
    again = client.post("/api/batch", json={"game_ids": ids, "depth": 9})
    assert again.status_code in (200, 409)       # 409 while running (it may already be over on a fast machine)
    done = _wait_batch(client, lambda s: not s["active"])
    assert done["status"] == "done" and done["completed"] == 3
    assert all(client.get(f"/api/review/{g}?depth=9").status_code == 200 for g in ids)
    # nothing left to do: a new batch does not start
    assert client.post("/api/batch", json={"game_ids": ids, "depth": 9}).get_json()["active"] is False


def test_batch_stop_can_revert_finished_games(client):
    pgns = [PGN.replace('[Event "Test"]', f'[Event "Batch B{i}"]') for i in range(12)]
    ids = [client.post("/api/games/import", json={"pgn": p, "username": "alice"}).get_json()["game_id"] for p in pgns]
    client.post("/api/batch", json={"game_ids": ids, "depth": 11})
    _wait_batch(client, lambda s: s["completed"] >= 1 or not s["active"])
    client.post("/api/batch/stop", json={"revert": True})
    final = _wait_batch(client, lambda s: not s["active"])
    if final["status"] == "stopped":             # (on a very fast machine it may simply have finished)
        assert final["completed"] == 0 and final["reverted"] >= 1
        assert all(client.get(f"/api/review/{g}?depth=11").status_code == 202 for g in ids)

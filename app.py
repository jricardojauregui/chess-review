"""Chess Review - Flask app.

Run with:  python app.py   (then open http://127.0.0.1:5050)
"""
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import config
from analysis import chesscom, explore, jobs, store
from analysis import stats as stats_mod
from analysis.engine import EngineNotFound
from analysis.review import PgnError, build_preview, build_review, meta_from_pgn, parse_pgn

app = Flask(__name__)
app.json.sort_keys = False
store.init()


def _error(message, status):
    return jsonify({"error": message}), status


def _depth(value, default=None):
    """Parse and clamp the ?depth= parameter."""
    try:
        depth = int(value)
    except (TypeError, ValueError):
        return default
    return max(config.DEPTH_MIN, min(config.DEPTH_MAX, depth))


@app.errorhandler(chesscom.ChessComError)
def _chesscom_error(exc):
    return _error(exc.message, exc.status)


@app.context_processor
def _inject_settings():
    """Every page gets the saved preferences (theme, board, linked account)."""
    settings = store.get_settings()
    settings["engine"] = config.preset(settings["engine"])["id"]
    settings["effort"] = config.effort(settings["effort"])["id"]
    return {"settings": settings, "config": config, "piece_sets": _piece_sets()}


def _piece_sets():
    """Piece sets present on disk (some are optional downloads) -> file extension."""
    sets = {}
    for folder in sorted((config.BASE_DIR / "static" / "img" / "pieces").iterdir()):
        king = next(folder.glob("wK.*"), None) if folder.is_dir() else None
        if king:
            sets[folder.name] = king.suffix.lstrip(".")
    return sets


def _account():
    account = store.get_settings()["account"]
    return account["username"] if account else None


# ----------------------------------------------------------------- pages
@app.route("/")
def page_home():
    return render_template("index.html")


@app.route("/review/<game_id>")
def page_review(game_id):
    return render_template("review.html", game_id=game_id)


@app.route("/stats")
def page_stats():
    return render_template("stats.html")


@app.route("/settings")
def page_settings():
    return render_template("settings.html")


@app.route("/puzzles")
def page_puzzles():
    return render_template("puzzles.html")


# ------------------------------------------------------------------- API
@app.route("/api/status")
def api_status():
    """Lets the UI warn early when Stockfish is missing."""
    path = config.find_stockfish()
    return jsonify({"stockfish": path, "ok": bool(path), "explore_engine_running": explore.is_running(),
                    "depth_default": config.DEPTH_DEFAULT, "depth_fast": config.DEPTH_FAST})


@app.route("/api/games/<username>")
def api_games(username):
    """Games of a chess.com user for one month (default: the latest one)."""
    username = chesscom.validate_username(username)
    archives = chesscom.get_archives(username)
    month = request.args.get("month") or (archives[0] if archives else None)
    if month is None:
        return jsonify({"username": username, "month": None, "archives": [], "games": []})
    games = chesscom.get_games(username, month)
    # Store every game so "Review" only needs its id (and stats can reuse them).
    ids = store.save_games(
        (g["pgn"], {k: v for k, v in g.items() if k != "pgn"}, username, g["end_time"])
        for g in games
    )
    analysed = store.analysed_game_ids(ids)
    listing = []
    for game_id, game in zip(ids, games):
        item = {k: v for k, v in game.items() if k != "pgn"}
        item["id"] = game_id
        item["analysed_depth"] = analysed.get(game_id)
        listing.append(item)
    return jsonify({"username": username, "month": month, "archives": archives,
                    "games": listing})


@app.route("/api/games/import", methods=["POST"])
def api_import():
    """Store a pasted PGN and return its game id."""
    body = request.get_json(silent=True) or {}
    pgn = (body.get("pgn") or "").strip()
    if not pgn:
        return _error("Paste a PGN first.", 400)
    try:
        game, _, _, _ = parse_pgn(pgn)
    except PgnError as exc:
        return _error(str(exc), 400)
    username = (body.get("username") or "").strip() or None
    meta = meta_from_pgn(game, username)
    game_id = store.save_game(pgn, meta, username if meta["hero"] else None)
    return jsonify({"game_id": game_id})


@app.route("/api/review/<game_id>")
def api_review(game_id):
    """The classified review, or 202 when the game still needs analysis."""
    row = store.get_game(game_id)
    if row is None:
        return _error("Game not found. Import it again from the home page.", 404)
    depths = store.analysed_depths(game_id)
    depth = _depth(request.args.get("depth")) or (depths[0] if depths else config.DEPTH_DEFAULT)
    positions = store.get_analysis(game_id, depth)
    if positions is None:
        # Not analysed yet: send the bare game so the board can be shown right away.
        try:
            preview = build_preview(row, request.args.get("hero"))
        except PgnError as exc:
            return _error(str(exc), 400)
        preview["pending_depth"] = depth
        return jsonify(preview), 202
    try:
        return jsonify(build_review(row, positions, depth, request.args.get("hero")))
    except PgnError as exc:
        return _error(str(exc), 400)


@app.route("/api/analyze/stream")
def api_analyze_stream():
    """Server-Sent Events: runs the engine and reports progress per move."""
    game_id = request.args.get("game_id", "")
    depth = _depth(request.args.get("depth"), config.DEPTH_DEFAULT)
    if store.get_game(game_id) is None:
        return _error("Game not found.", 404)
    if store.get_analysis(game_id, depth) is not None:
        done = jobs._event("done", {"status": "done", "cached": True})
        return Response(done, mimetype="text/event-stream")
    job = jobs.start(game_id, depth)
    return Response(stream_with_context(jobs.stream(job)), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/batch", methods=["GET", "POST"])
def api_batch():
    """State of the batch analysis, or (POST {game_ids, depth}) start one."""
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        ids = [g for g in (body.get("game_ids") or []) if isinstance(g, str)][:200]
        depth = _depth(body.get("depth"), config.DEPTH_DEFAULT)
        if not config.find_stockfish():
            return _error("Stockfish was not found. Set STOCKFISH_PATH in .env (see README).", 503)
        state, started = jobs.start_batch(ids, depth)
        if not started and state.get("active"):
            return jsonify({**state, "error": "An analysis is already running."}), 409
        return jsonify(state)
    return jsonify(jobs.batch_state())


@app.route("/api/batch/stop", methods=["POST"])
def api_batch_stop():
    """Stop the batch; {revert: true} also discards the games it had finished."""
    body = request.get_json(silent=True) or {}
    return jsonify(jobs.stop_batch(revert=body.get("revert")))


@app.route("/api/games/lookup", methods=["POST"])
def api_lookup():
    """Import one specific chess.com game by its id or URL."""
    body = request.get_json(silent=True) or {}
    item = chesscom.get_game_by_id(body.get("ref"), _account())
    meta = {k: v for k, v in item.items() if k != "pgn"}
    game_id = store.save_game(item["pgn"], meta, _account() if item["hero"] else None,
                              item["end_time"])
    return jsonify({"game_id": game_id})


@app.route("/api/explore", methods=["POST"])
def api_explore():
    """Engine lines for any position (used when the user tries their own moves)."""
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(explore.analyse_fen(body.get("fen") or ""))
    except EngineNotFound as exc:
        return _error(str(exc), 503)
    except ValueError:
        return _error("That position is not valid.", 400)


@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    """Read or change preferences (theme, board, pieces, sound, menu)."""
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        allowed = {k: v for k, v in body.items()
                   if k in ("theme", "board", "pieces", "sound", "engine", "effort")}
        if "engine" in allowed:
            allowed["engine"] = config.preset(allowed["engine"])["id"]
        if "effort" in allowed:
            allowed["effort"] = config.effort(allowed["effort"])["id"]
        return jsonify(store.update_settings(allowed))
    return jsonify(store.get_settings())


@app.route("/api/account", methods=["POST", "DELETE"])
def api_account():
    """Link (POST {username}) or unlink (DELETE) the chess.com account."""
    if request.method == "DELETE":
        return jsonify(store.update_settings({"account": None}))
    body = request.get_json(silent=True) or {}
    username = chesscom.validate_username(body.get("username"))
    player = chesscom.get_player(username)          # 404s for unknown users
    store.save_player(player["username"], player)
    account = {"username": player["username"], "avatar": player.get("avatar"),
               "name": player.get("name")}
    return jsonify(store.update_settings({"account": account}))


@app.route("/api/player/<username>")
def api_player(username):
    """chess.com profile (avatar), cached for a week."""
    username = chesscom.validate_username(username)
    player = store.get_player(username)
    if player is None:
        try:
            player = chesscom.get_player(username)
        except chesscom.ChessComError:
            player = {"username": username, "avatar": None}
        store.save_player(username, player)
    return jsonify(player)


@app.route("/api/stats/<username>")
def api_stats(username):
    username = chesscom.validate_username(username)
    limit = request.args.get("n", type=int) or config.STATS_DEFAULT_GAMES
    return jsonify(stats_mod.build_stats(username, limit))


@app.route("/api/puzzles/<username>")
def api_puzzles(username):
    username = chesscom.validate_username(username)
    limit = request.args.get("n", type=int) or config.STATS_DEFAULT_GAMES
    return jsonify({"username": username,
                    "puzzles": stats_mod.build_puzzles(username, limit)})


if __name__ == "__main__":
    if not config.find_stockfish():
        print("WARNING: Stockfish not found. Set STOCKFISH_PATH in .env (see README).")
    print(f"Chess Review running at http://{config.HOST}:{config.PORT}")
    try:
        app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)
    finally:
        explore.shutdown()      # otherwise Ctrl+C leaves the process hanging

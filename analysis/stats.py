"""Phase 6 extras: statistics over the user's analysed games and puzzles
generated from their own blunders and misses."""
import config
from analysis import classify as C
from analysis import store
from analysis.review import cached_review

_ERRORS = (C.MISTAKE, C.BLUNDER, C.MISS)


def recent_reviews(username, limit):
    """Reviews (deepest cached analysis) of the user's latest analysed games."""
    reviews = []
    for row in store.games_for_user(username, limit, analysed_only=True):
        depths = store.analysed_depths(row["id"])
        review = cached_review(row["id"], depths[0]) if depths else None
        if review and review["hero"] in ("w", "b"):
            reviews.append(review)
    return reviews


def hero_rating(reviews):
    """The user's rating in the most recent reviewed game that has one."""
    for review in reviews:
        side = "white" if review["hero"] == "w" else "black"
        rating = (review["game"].get(side) or {}).get("rating")
        if rating:
            return rating
    return None


def _base_seconds(time_control):
    """Base time in seconds from a PGN TimeControl ("600+5"); None for daily."""
    if not time_control or "/" in time_control:
        return None
    try:
        return int(time_control.split("+")[0])
    except ValueError:
        return None


def _outcome(result, hero):
    if result == "1/2-1/2":
        return "draw"
    if result in ("1-0", "0-1"):
        return "win" if (result == "1-0") == (hero == "w") else "loss"
    return "other"


def build_stats(username, limit=None):
    """Aggregate numbers for the stats page."""
    limit = limit or config.STATS_DEFAULT_GAMES
    reviews = recent_reviews(username, limit)
    totals = {label: 0 for label in C.ALL_LABELS}
    outcomes = {"win": 0, "draw": 0, "loss": 0}
    openings, games = {}, []
    accuracies = []
    by_color = {"w": [], "b": []}
    clock = {"pressure": {"moves": 0, "errors": 0, "acc": 0.0},
             "normal": {"moves": 0, "errors": 0, "acc": 0.0}}

    for review in reviews:
        hero, meta = review["hero"], review["game"]
        accuracy = review["summary"]["accuracy"][hero]
        counts = review["summary"]["counts"][hero]
        outcome = _outcome(meta.get("result"), hero)
        for label, n in counts.items():
            totals[label] += n
        if outcome in outcomes:
            outcomes[outcome] += 1
        if accuracy is not None:
            accuracies.append(accuracy)
            by_color[hero].append(accuracy)

        # Opening family = name before the first ":" (variation)
        book = meta.get("opening_book")
        name = (book["name"].split(":")[0] if book else meta.get("opening")) or "Unknown"
        entry = openings.setdefault(name, {"name": name, "games": 0, "win": 0, "draw": 0,
                                           "loss": 0, "acc": []})
        entry["games"] += 1
        if outcome in outcomes:
            entry[outcome] += 1
        if accuracy is not None:
            entry["acc"].append(accuracy)

        # Errors under time pressure (needs %clk in the PGN)
        base = _base_seconds(meta.get("time_control"))
        if base:
            limit_seconds = max(base * config.TIME_PRESSURE_FRACTION,
                                config.TIME_PRESSURE_MIN_SECONDS)
            for move in review["moves"]:
                if move["color"] != hero or move.get("clock") is None or move["cls"] == C.BOOK:
                    continue
                bucket = clock["pressure" if move["clock"] <= limit_seconds else "normal"]
                bucket["moves"] += 1
                bucket["acc"] += move["accuracy"]
                bucket["errors"] += move["cls"] in _ERRORS

        opponent = meta["black" if hero == "w" else "white"]
        games.append({
            "id": meta["id"], "date": meta.get("date"), "color": hero,
            "opponent": opponent["name"], "opponent_rating": opponent.get("rating"),
            "outcome": outcome, "accuracy": accuracy, "opening": name,
            "blunders": counts[C.BLUNDER], "mistakes": counts[C.MISTAKE],
            "misses": counts[C.MISS], "depth": review["depth"],
            "result": meta.get("result"), "termination": meta.get("termination"),
            # for the hover preview of the final position
            "final_fen": review["moves"][-1]["fen_after"] if review["moves"] else None,
        })

    n = len(reviews)
    mean = lambda values: round(sum(values) / len(values), 1) if values else None
    opening_rows = []
    for entry in openings.values():
        entry["accuracy"] = mean(entry.pop("acc"))
        entry["loss_rate"] = round(100 * entry["loss"] / entry["games"])
        opening_rows.append(entry)
    opening_rows.sort(key=lambda e: (-e["loss"], -e["loss_rate"], -e["games"]))

    pressure = {}
    for key, bucket in clock.items():
        moves = bucket["moves"]
        pressure[key] = {
            "moves": moves,
            "errors": bucket["errors"],
            "error_rate": round(100 * bucket["errors"] / moves, 1) if moves else None,
            "accuracy": round(bucket["acc"] / moves, 1) if moves else None,
        }

    return {
        "username": username,
        "games": n,
        "accuracy": mean(accuracies),
        "accuracy_white": mean(by_color["w"]),
        "accuracy_black": mean(by_color["b"]),
        "outcomes": outcomes,
        "blunders_per_game": round(totals[C.BLUNDER] / n, 2) if n else None,
        "mistakes_per_game": round(totals[C.MISTAKE] / n, 2) if n else None,
        "misses_per_game": round(totals[C.MISS] / n, 2) if n else None,
        "totals": totals,
        "openings": opening_rows,
        "time_pressure": pressure,
        "game_list": games,
    }


def build_puzzles(username, limit=None):
    """One puzzle per Blunder / Miss the user played: find the best move."""
    puzzles = []
    for review in recent_reviews(username, limit or config.STATS_DEFAULT_GAMES):
        hero, meta = review["hero"], review["game"]
        opponent = meta["black" if hero == "w" else "white"]["name"]
        for move in review["moves"]:
            if move["color"] != hero or move["cls"] not in (C.BLUNDER, C.MISS):
                continue
            if not move.get("best"):
                continue
            puzzles.append({
                "id": f"{meta['id']}-{move['ply']}",
                "game_id": meta["id"], "ply": move["ply"],
                "move_number": move["move_number"], "color": hero,
                "fen": move["fen_before"],
                "played": move["san"], "cls": move["cls"],
                "best": move["best"]["san"], "best_uci": move["best"]["uci"],
                "good_moves": move["good_moves"],
                "line": move["best"]["pv_san"],
                "eval": move["best"]["eval"]["text"],
                "opponent": opponent, "date": meta.get("date"),
            })
    return puzzles

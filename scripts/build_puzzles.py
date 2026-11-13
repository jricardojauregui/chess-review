"""Build data/puzzles.tsv, the bank of training puzzles.

    python scripts/build_puzzles.py            # downloads the start of the database
    python scripts/build_puzzles.py file.csv   # or use a CSV you already have

The source is the Lichess puzzle database (https://database.lichess.org/#puzzles,
public domain / CC0): positions from real games with a single winning line,
each tagged with themes and a difficulty rating. Only the beginning of the
file is downloaded (it is sorted by a random id, so that is a fair sample);
it needs the `zstd` command to decompress.

From it we keep well-liked, well-tested puzzles between RATING_MIN and
RATING_MAX, balanced across difficulty bands and the themes the app trains,
check that every move is legal, and write one puzzle per line:

    id <TAB> fen <TAB> moves (UCI) <TAB> rating <TAB> themes

The FEN is the position BEFORE the opponent's move: moves[0] is played for
the opponent, then the solver and the opponent alternate.
"""
import csv
import random
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import chess

URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
USER_AGENT = "chess-review-personal/1.0"
DOWNLOAD_BYTES = 16_000_000
OUT = Path(__file__).resolve().parent.parent / "data" / "puzzles.tsv"

RATING_MIN, RATING_MAX, BAND = 400, 2200, 100
PER_BAND = 520                       # puzzles kept per 100 rating points
MIN_POPULARITY, MIN_PLAYS, MAX_DEVIATION = 85, 300, 95
MAX_SOLVER_MOVES = 5
# Themes the trainer can focus on: each band keeps a minimum of every one
FOCUS_THEMES = ["mateIn1", "mateIn2", "mateIn3", "backRankMate", "hangingPiece", "fork", "pin",
                "skewer", "discoveredAttack", "trappedPiece", "defensiveMove", "opening",
                "endgame", "promotion", "sacrifice", "deflection"]
PER_THEME = 22
DROP_THEMES = {"master", "masterVsMaster", "superGM"}


def download(target):
    """First DOWNLOAD_BYTES of the compressed database -> CSV (the cut-off row is dropped)."""
    request = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT,
                                                   "Range": f"bytes=0-{DOWNLOAD_BYTES - 1}"})
    packed = target.with_suffix(".zst")
    with urllib.request.urlopen(request, timeout=120) as response:
        packed.write_bytes(response.read())
    with open(target, "wb") as out:      # zstd complains about the truncated end: expected
        subprocess.run(["zstd", "-dc", str(packed)], stdout=out, stderr=subprocess.DEVNULL)
    return target


def legal(fen, moves):
    """True when every move of the line can be played from the position."""
    try:
        board = chess.Board(fen)
        for uci in moves:
            board.push_uci(uci)
    except ValueError:
        return False
    return True


def candidates(path):
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                rating, deviation = int(row["Rating"]), int(row["RatingDeviation"])
                popularity, plays = int(row["Popularity"]), int(row["NbPlays"])
            except (TypeError, ValueError, KeyError):
                continue                                  # the truncated last row
            moves = (row["Moves"] or "").split()
            solver = len(moves) // 2
            if not (RATING_MIN <= rating < RATING_MAX and deviation <= MAX_DEVIATION
                    and popularity >= MIN_POPULARITY and plays >= MIN_PLAYS
                    and len(moves) % 2 == 0 and 1 <= solver <= MAX_SOLVER_MOVES):
                continue
            themes = [t for t in row["Themes"].split() if t not in DROP_THEMES]
            yield {"id": row["PuzzleId"], "fen": row["FEN"], "moves": moves,
                   "rating": rating, "themes": themes}


def select(pool, rng):
    """Balanced pick: per rating band, some of every focus theme, then the best mix."""
    bands = {}
    for puzzle in pool:
        bands.setdefault(puzzle["rating"] // BAND, []).append(puzzle)
    chosen = []
    for band in sorted(bands):
        items = bands[band]
        rng.shuffle(items)
        picked, ids = [], set()

        def take(puzzle):
            if puzzle["id"] not in ids and legal(puzzle["fen"], puzzle["moves"]):
                ids.add(puzzle["id"])
                picked.append(puzzle)

        for theme in FOCUS_THEMES:
            wanted = [p for p in items if theme in p["themes"]]
            # longer lines first: they are the interactive ones
            wanted.sort(key=lambda p: -len(p["moves"]))
            for puzzle in wanted[:PER_THEME]:
                take(puzzle)
        for puzzle in items:
            if len(picked) >= PER_BAND:
                break
            take(puzzle)
        chosen.extend(picked)
    return chosen


def main():
    rng = random.Random(2026)
    if len(sys.argv) > 1:
        source = Path(sys.argv[1])
    else:
        print("Downloading the start of the Lichess puzzle database...")
        source = download(Path(tempfile.mkdtemp(prefix="puzzles-")) / "puzzles.csv")
    pool = list(candidates(source))
    chosen = select(pool, rng)
    rng.shuffle(chosen)
    with open(OUT, "w", encoding="utf-8", newline="\n") as out:
        for p in chosen:
            out.write("\t".join([p["id"], p["fen"], " ".join(p["moves"]), str(p["rating"]),
                                 " ".join(p["themes"])]) + "\n")
    multi = sum(len(p["moves"]) > 2 for p in chosen)
    print(f"{len(pool)} candidates -> {len(chosen)} puzzles ({multi} with several moves) in {OUT}")


if __name__ == "__main__":
    main()

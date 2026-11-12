"""Central configuration for Chess Review.

Every tunable number (engine settings, classification thresholds, accuracy
formula constants) lives here so it can be adjusted without touching the logic.
"""
import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
OPENINGS_DIR = DATA_DIR / "openings"
DB_PATH = Path(os.environ.get("CHESS_REVIEW_DB", DATA_DIR / "cache.db"))


def find_stockfish():
    """Return the Stockfish binary path, or None when it cannot be found.

    Order: STOCKFISH_PATH (env / .env) -> PATH -> common install locations.
    """
    env_path = os.environ.get("STOCKFISH_PATH")
    if env_path and Path(env_path).is_file():
        return env_path
    on_path = shutil.which("stockfish")
    if on_path:
        return on_path
    candidates = [
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
        "/usr/bin/stockfish",
        "/usr/games/stockfish",
        r"C:\Program Files\Stockfish\stockfish.exe",
        r"C:\stockfish\stockfish.exe",
        str(BASE_DIR / "stockfish"),
        str(BASE_DIR / "stockfish.exe"),
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    return None


# --------------------------------------------------------------------------
# chess.com API
# --------------------------------------------------------------------------
CHESSCOM_API = "https://api.chess.com/pub"
USER_AGENT = "chess-review-personal/1.0"
HTTP_TIMEOUT = 20  # seconds

# --------------------------------------------------------------------------
# Engine
# --------------------------------------------------------------------------
# Analysis levels offered in the UI. Each one is a search depth plus a hard time
# cap per position, so even the deepest level has a bounded cost. "seconds" is
# the measured average per position on an Apple M5 (one thread).
ENGINE_PRESETS = [
    {"id": "lite", "name": "Lite", "depth": 10, "max_seconds": 0.5, "seconds": 0.03,
     "blurb": "A quick look. Catches the obvious blunders.", "cost": 1},
    {"id": "fast", "name": "Fast", "depth": 12, "max_seconds": 1.0, "seconds": 0.06,
     "blurb": "Good for casual review and for batches of games.", "cost": 2},
    {"id": "standard", "name": "Standard", "depth": 16, "max_seconds": 3.0, "seconds": 0.6,
     "blurb": "The best balance of speed and accuracy.", "cost": 3},
    {"id": "deep", "name": "Deep", "depth": 20, "max_seconds": 8.0, "seconds": 2.0,
     "blurb": "Sees long tactics. Takes a few minutes per game.", "cost": 4},
    {"id": "max", "name": "Max", "depth": 24, "max_seconds": 20.0, "seconds": 8.5,
     "blurb": "Everything the engine has. Slow: use it for the games that matter.", "cost": 5},
]
DEFAULT_PRESET = "standard"
DEPTH_DEFAULT = 16                  # depth of DEFAULT_PRESET
DEPTH_FAST = 12
DEPTH_MIN, DEPTH_MAX = 6, 26
MULTIPV = 2
PV_LENGTH = 6                       # plies of principal variation stored per line
# One thread is the default on purpose: fixed-depth MultiPV searches with several
# threads were measured ~3x slower overall (some tactical positions took 20s+).
ENGINE_THREADS = int(os.environ.get("ENGINE_THREADS", "1"))
ENGINE_HASH_MB = 256                # per engine; shared out when several run at once
ENGINE_HASH_MIN_MB = 64

# Effort = how much of the CPU an analysis may use (speed, not quality). The
# positions of a game are shared out between several single-threaded Stockfish
# processes; the results are the same kind as with one, they just arrive sooner.
# "share" is the fraction of the FAST cores used (on Apple Silicon the
# efficiency cores are never counted, so the system always has room to breathe).
EFFORT_LEVELS = [
    {"id": "low", "name": "Low", "share": 0.0,
     "blurb": "One engine. Quiet and cool; the slowest."},
    {"id": "medium", "name": "Medium", "share": 0.5,
     "blurb": "Half of the fast cores. A good everyday balance."},
    {"id": "high", "name": "High", "share": 0.75,
     "blurb": "Most of the fast cores. Fans may spin up on long analyses."},
    {"id": "max", "name": "Max", "share": 1.0,
     "blurb": "Every fast core. The quickest; the computer runs warm meanwhile."},
]
DEFAULT_EFFORT = "medium"
# Hard ceiling on parallel engines, whatever the effort (0 = no extra ceiling).
ENGINE_MAX_WORKERS = int(os.environ.get("ENGINE_MAX_WORKERS", "0"))
MAX_SECONDS_PER_POSITION = 6.0      # cap for depths that are not a preset
# Run Stockfish at a lower OS priority ("nice") so the rest of the computer stays
# responsive while it thinks. 0 disables it. (Unix only; ignored on Windows.)
ENGINE_NICE = 10

# Win% model: win% = 50 + 50 * (2 / (1 + exp(-WIN_K * cp)) - 1)
WIN_K = 0.00368208
MATE_CP = 10000                     # a forced mate counts as +/- this many cp

# --------------------------------------------------------------------------
# Classification thresholds (all "loss"/"gap" numbers are win% points)
# --------------------------------------------------------------------------
# Loss ladder: loss < value -> that label; anything >= MISTAKE_MAX is a blunder.
EXCELLENT_MAX = 2.0
GOOD_MAX = 5.0
INACCURACY_MAX = 10.0
MISTAKE_MAX = 20.0

# Brilliant
BRILLIANT_MAX_LOSS = 2.0            # must be best, or lose at most this much
BRILLIANT_MAX_WIN_BEFORE = 95.0     # not brilliant if it was already winning
BRILLIANT_MIN_WIN_AFTER = 50.0      # must not leave you worse
SACRIFICE_MIN_POINTS = 2            # net material offered (pawn=1 ... queen=9)
SACRIFICE_MIN_PIECE_VALUE = 3       # ignore pawn sacrifices (trivial)
SACRIFICE_PV_PLIES = 4              # how far into the PV to look for the material drop

# Great - follows chess.com's published definition: a move "critical to the
# outcome of the game" (losing -> equal, equal -> winning, or the only good
# move). In practice: it is the best move, the second best is much worse, and
# that difference actually changes the outcome.
GREAT_MIN_GAP = 15.0                # best move vs second best (win%)
GREAT_MIN_WIN_BEST = 30.0           # the best move must not still be losing...
GREAT_MAX_WIN_SECOND = 70.0         # ...and the alternative must not still be winning
# Obvious moves are never Great: recaptures, mate in one, and simply moving an
# attacked piece to safety (without capturing or giving check).
GREAT_SKIP_OBVIOUS = True

# Miss
MISS_MIN_OPPORTUNITY = 15.0         # win% the opponent's error handed you
MISS_MIN_LOSS = 10.0                # ...and how much of it you let slip
# A forced mate in <= N that is no longer a mate after the move counts as a Miss
# even when the position is still winning. Set to 0 to disable.
MISSED_MATE_MAX_N = 5

# Context tags
TACTIC_MIN_POINTS = 2               # material won in the PV to call it a tactic
RETRY_TOLERANCE = 2.0               # "Retry" accepts moves within this win% of best

# Accuracy per move = clamp(A * exp(-B * loss) - C, 0, 100)
ACC_A, ACC_B, ACC_C = 103.1668, 0.04354, 3.1669
# Game accuracy. chess.com's CAPS2 formula is not public, so both options were
# measured against the accuracy chess.com itself reports for real games:
#   "weighted": critical positions count more and the harmonic mean is blended
#               in (single blunders hurt a lot). Off by ~5 points on average.
#   "mean":     plain average of the move accuracies. Off by ~18 points (too high).
ACCURACY_MODE = "weighted"
# The starting position always shows 0.00 (like chess.com) instead of the
# engine's small first-move edge.
START_EVAL_ZERO = True

# Live exploration on the review board ("what if I had played...")
EXPLORE_DEPTH = 16
EXPLORE_MULTIPV = 3
EXPLORE_MAX_SECONDS = 2.5
# The live-exploration engine is stopped after this long without a request, so
# nothing keeps running (or holding memory) while you are not using it.
EXPLORE_IDLE_SECONDS = 90

# Game phases (Lichess-style divider)
ENDGAME_MAX_PIECES = 6              # majors+minors on the board (both sides)
MIDDLEGAME_MAX_PIECES = 10
OPENING_MAX_PLY = 30                # the opening never lasts longer than this
# Quality icon per game phase: first entry whose minimum accuracy is reached.
PHASE_QUALITY = [(90, "best"), (80, "excellent"), (70, "good"),
                 (55, "inaccuracy"), (40, "mistake"), (0, "blunder")]

# --------------------------------------------------------------------------
# Stats (phase 6)
# --------------------------------------------------------------------------
TIME_PRESSURE_FRACTION = 0.10       # clock below 10% of the base time...
TIME_PRESSURE_MIN_SECONDS = 10      # ...or below this many seconds
STATS_DEFAULT_GAMES = 20

# --------------------------------------------------------------------------
# Web server
# --------------------------------------------------------------------------
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5050"))   # 5000 is taken by AirPlay on macOS


def preset(preset_id):
    """Preset dict by id (falls back to the default preset)."""
    for item in ENGINE_PRESETS:
        if item["id"] == preset_id:
            return item
    return preset(DEFAULT_PRESET)


@functools.lru_cache(maxsize=1)
def performance_cores():
    """Number of fast CPU cores.

    On Apple Silicon this is the performance tier only (efficiency cores are
    left for the rest of the system); elsewhere, the physical cores as best we
    can tell (half the logical ones when hyper-threading is likely).
    """
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                                 capture_output=True, text=True, timeout=2).stdout.strip()
            if out.isdigit() and int(out) > 0:
                return int(out)
        except (OSError, subprocess.SubprocessError):
            pass
    logical = os.cpu_count() or 1
    return max(1, logical // 2) if logical > 2 else logical


def effort_levels():
    """EFFORT_LEVELS with the number of parallel engines each one means here."""
    cores = performance_cores()
    levels, previous = [], 1
    for item in EFFORT_LEVELS:
        workers = max(previous, 1, round(cores * item["share"]))
        if ENGINE_MAX_WORKERS:
            workers = min(workers, ENGINE_MAX_WORKERS)
        previous = workers
        levels.append({**item, "workers": workers})
    return levels


def effort(effort_id):
    """Effort dict by id (falls back to the default effort)."""
    levels = effort_levels()
    for item in levels:
        if item["id"] == effort_id:
            return item
    return next(item for item in levels if item["id"] == DEFAULT_EFFORT)


def hash_mb_for(workers):
    """Hash per engine when ``workers`` of them run at the same time."""
    return max(ENGINE_HASH_MIN_MB, ENGINE_HASH_MB // max(1, workers))


def max_seconds_for_depth(depth):
    """Per-position time cap that goes with a search depth."""
    for item in ENGINE_PRESETS:
        if item["depth"] == depth:
            return item["max_seconds"]
    return MAX_SECONDS_PER_POSITION

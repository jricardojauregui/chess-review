"""Download the optional piece sets that are not shipped with the project.

    python scripts/fetch_pieces.py

- "neo" and "neo_wood" are chess.com's own piece sets. They are fetched from
  chess.com's public image server for personal use on this computer and are
  NOT part of the repository (see .gitignore): they belong to chess.com.
- The other sets come from the open-source Lichess project (lichess-org/lila).

Sets whose folder is missing simply do not show up in Settings.
"""
import sys
import urllib.request
from pathlib import Path

PIECES_DIR = Path(__file__).resolve().parent.parent / "static" / "img" / "pieces"
CODES = [color + piece for color in "wb" for piece in "KQRBNP"]
USER_AGENT = "chess-review-personal/1.0"

CHESSCOM = "https://images.chesscomfiles.com/chess-themes/pieces/{set}/150/{code}.png"
LICHESS = "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece/{set}/{code}.svg"
SETS = {
    "neo": ("png", lambda code: CHESSCOM.format(set="neo", code=code.lower())),
    "neo_wood": ("png", lambda code: CHESSCOM.format(set="neo_wood", code=code.lower())),
    "dubrovny": ("svg", lambda code: LICHESS.format(set="dubrovny", code=code)),
    "chessnut": ("svg", lambda code: LICHESS.format(set="chessnut", code=code)),
    "leipzig": ("svg", lambda code: LICHESS.format(set="leipzig", code=code)),
}


def fetch(name):
    ext, url_for = SETS[name]
    folder = PIECES_DIR / name
    folder.mkdir(parents=True, exist_ok=True)
    for code in CODES:
        target = folder / f"{code}.{ext}"
        if target.exists() and target.stat().st_size > 0:
            continue
        request = urllib.request.Request(url_for(code), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            target.write_bytes(response.read())
    print(f"{name}: ok")


if __name__ == "__main__":
    failed = False
    for set_name in sys.argv[1:] or SETS:
        try:
            fetch(set_name)
        except Exception as exc:          # keep going: the other sets may still work
            failed = True
            print(f"{set_name}: FAILED ({exc})")
    sys.exit(1 if failed else 0)

"""Opening lessons: the coach's hand-written courses (lessons_data.py), an
automatic explainer for every other named opening (the Lichess TSV database)
and the link between both and the user's own games ("openings that fit me").
"""
import csv
import threading
from functools import lru_cache

import chess
import chess.pgn
import io

import config
from analysis import store
from analysis.lessons_data import LESSONS

PIECE_NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
               chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5,
                chess.QUEEN: 9, chess.KING: 100}
CENTRE = {chess.D4, chess.E4, chess.D5, chess.E5}
FAMILY_NAMES = {"e4": "White · 1.e4", "d4": "White · 1.d4", "flank": "White · flank openings",
                "vs_e4": "Black · against 1.e4", "vs_d4": "Black · against 1.d4"}
LEVEL_NAMES = {1: "Easy to learn", 2: "Some study", 3: "Demanding"}
GAME_PLIES = 16                     # how much of each game is kept for matching


# --------------------------------------------------------------------------
# Automatic move explainer (for openings without a hand-written lesson)
# --------------------------------------------------------------------------
def _attacked_target(board, square, color):
    """Most valuable enemy piece the piece on ``square`` attacks profitably."""
    best = None
    mover = board.piece_at(square)
    for target in board.attacks(square):
        piece = board.piece_at(target)
        if piece is None or piece.color == color or piece.piece_type == chess.KING:
            continue
        defended = board.is_attacked_by(not color, target)
        if defended and PIECE_VALUES[piece.piece_type] <= PIECE_VALUES[mover.piece_type]:
            continue                                  # a defended piece of lower value: no threat
        if best is None or PIECE_VALUES[piece.piece_type] > PIECE_VALUES[best[0].piece_type]:
            best = (piece, target)
    return best


def _pinned_knight(board, square, color):
    """Square of an enemy knight this bishop pins to the queen or king, if any."""
    for target in board.attacks(square):
        piece = board.piece_at(target)
        if piece is None or piece.color == color or piece.piece_type != chess.KNIGHT:
            continue
        step_file = chess.square_file(target) - chess.square_file(square)
        step_rank = chess.square_rank(target) - chess.square_rank(square)
        df = (step_file > 0) - (step_file < 0)
        dr = (step_rank > 0) - (step_rank < 0)
        f, r = chess.square_file(target) + df, chess.square_rank(target) + dr
        while 0 <= f < 8 and 0 <= r < 8:
            behind = board.piece_at(chess.square(f, r))
            if behind is not None:
                if behind.color != color and behind.piece_type in (chess.QUEEN, chess.KING):
                    return target, behind.piece_type
                break
            f, r = f + df, r + dr
    return None


# Spanish for every sentence of the automatic explainer (key = the English template)
PIECES_ES = {chess.PAWN: "el peón", chess.KNIGHT: "el caballo", chess.BISHOP: "el alfil",
             chess.ROOK: "la torre", chess.QUEEN: "la dama", chess.KING: "el rey"}
EXPLAIN_ES = {
    "Castles: the king is safe and the rook joins the game.": "Enroque: el rey queda seguro y la torre entra en juego.",
    "Takes en passant, removing the pawn that just ran past.": "Captura al paso, eliminando el peón que acaba de pasar de largo.",
    "Recaptures on {sq}, keeping material level.": "Recaptura en {sq} y mantiene el material igualado.",
    "Takes the {piece} and brings a pawn to the centre.": "Captura {piece} y lleva un peón al centro.",
    "Trades pawns on {sq}, changing the structure and opening lines.": "Cambia peones en {sq}: cambia la estructura y abre líneas.",
    "Takes the {piece} on {sq}.": "Captura {piece} de {sq}.",
    "Attacks the {piece} on {sq} and asks it where it is going.": "Ataca {piece} de {sq} y le pregunta adónde va.",
    "Fights for the centre and challenges the pawn on {sq}.": "Lucha por el centro y desafía al peón de {sq}.",
    "Takes space in the centre and opens lines for the pieces behind it.": "Gana espacio en el centro y abre líneas para las piezas de atrás.",
    "Fights for the centre from the side, without committing the central pawns.": "Lucha por el centro desde el flanco, sin comprometer los peones centrales.",
    "Gains space on the kingside and eyes the centre, at the cost of loosening the king a little.": "Gana espacio en el flanco de rey y mira al centro, a cambio de debilitar un poco al rey.",
    "Prepares a fianchetto: the bishop will sit on the long diagonal.": "Prepara un fianchetto: el alfil se instalará en la gran diagonal.",
    "A useful waiting move: it takes the {sq} square away from the enemy pieces.": "Una jugada de espera útil: le quita la casilla {sq} a las piezas rivales.",
    "A solid move: it supports the centre and opens a diagonal for a bishop.": "Una jugada sólida: apoya el centro y abre una diagonal para un alfil.",
    "Pushes forward to gain space and cramp the opponent.": "Avanza para ganar espacio y apretar al rival.",
    "Challenges the pawn on {sq}.": "Desafía al peón de {sq}.",
    "A pawn move that shapes the structure and prepares the next piece.": "Una jugada de peón que define la estructura y prepara la siguiente pieza.",
    "Develops the knight toward the centre": "Desarrolla el caballo hacia el centro",
    "The knight heads for a better square": "El caballo va a una casilla mejor",
    "The knight takes a strong central square": "El caballo ocupa una fuerte casilla central",
    "{base}, attacking the {piece} on {sq}.": "{base}, atacando {piece} de {sq}.",
    "{base} and protects the pawn on {sq}.": "{base} y protege el peón de {sq}.",
    "{base}.": "{base}.",
    "Pins the knight on {sq} to the {piece}: it cannot move freely now.": "Clava el caballo de {sq} contra {piece}: ya no puede moverse con libertad.",
    "The bishop settles on the long diagonal, where it works across the whole board.": "El alfil se instala en la gran diagonal, desde donde actúa en todo el tablero.",
    "The bishop comes out and attacks the {piece} on {sq}.": "El alfil sale y ataca {piece} de {sq}.",
    "Develops the bishop to its most active diagonal, looking at {sq}.": "Desarrolla el alfil a su diagonal más activa, mirando a {sq}.",
    "Develops the bishop and clears the way to castle.": "Desarrolla el alfil y despeja el camino para enrocar.",
    "The bishop moves to a safer or more useful diagonal.": "El alfil pasa a una diagonal más segura o más útil.",
    "The queen comes out with a threat on the {piece} on {sq}.": "La dama sale amenazando {piece} de {sq}.",
    "The queen comes out early. It is active here, but make sure it cannot be chased around.": "La dama sale pronto. Aquí es activa, pero cuida que no la puedan perseguir.",
    "Brings the queen to a more active square.": "Lleva la dama a una casilla más activa.",
    "The rook takes the open file.": "La torre ocupa la columna abierta.",
    "The rook goes to the half-open file, where it presses on the enemy pawn.": "La torre va a la columna semiabierta, donde presiona al peón rival.",
    "The rook moves toward the centre, behind the pawns it will support.": "La torre se acerca al centro, detrás de los peones que va a apoyar.",
    "The king steps aside.": "El rey se aparta.",
    " Checkmate!": " ¡Jaque mate!",
    " With check.": " Con jaque.",
}


def explain_move(board, move, lang="en"):
    """A short, principle-based explanation of an opening move (before it is played)."""
    spanish = lang == "es"

    def say(template, piece=None, **values):
        """The sentence in the chosen language; ``piece`` is a chess piece type."""
        if spanish:
            return EXPLAIN_ES[template].format(piece=PIECES_ES.get(piece), **values)
        return template.format(piece=PIECE_NAMES.get(piece), **values)

    color = board.turn
    piece = board.piece_at(move.from_square)
    kind = piece.piece_type
    to_name = chess.square_name(move.to_square)
    captured = board.piece_at(move.to_square)
    last = board.peek() if board.move_stack else None
    recapture = bool(captured and last and last.to_square == move.to_square and board.is_capture(last)) \
        if last else False
    after = board.copy(stack=False)
    after.push(move)
    home_rank = 0 if color == chess.WHITE else 7
    from_rank, to_rank = chess.square_rank(move.from_square), chess.square_rank(move.to_square)
    to_file = chess.square_file(move.to_square)
    target = _attacked_target(after, move.to_square, color)
    target_piece = target[0].piece_type if target else None
    target_sq = chess.square_name(target[1]) if target else None

    if board.is_castling(move):
        text = say("Castles: the king is safe and the rook joins the game.")
    elif board.is_en_passant(move):
        text = say("Takes en passant, removing the pawn that just ran past.")
    elif captured:
        if recapture:
            text = say("Recaptures on {sq}, keeping material level.", sq=to_name)
        elif kind == chess.PAWN and move.to_square in CENTRE:
            text = say("Takes the {piece} and brings a pawn to the centre.", captured.piece_type)
        elif kind == chess.PAWN and captured.piece_type == chess.PAWN:
            text = say("Trades pawns on {sq}, changing the structure and opening lines.", sq=to_name)
        else:
            text = say("Takes the {piece} on {sq}.", captured.piece_type, sq=to_name)
    elif kind == chess.PAWN:
        forward = to_rank if color == chess.WHITE else 7 - to_rank
        if target and target_piece != chess.PAWN:
            text = say("Attacks the {piece} on {sq} and asks it where it is going.", target_piece, sq=target_sq)
        elif move.to_square in CENTRE:
            if target:
                text = say("Fights for the centre and challenges the pawn on {sq}.", sq=target_sq)
            else:
                text = say("Takes space in the centre and opens lines for the pieces behind it.")
        elif to_file in (2, 5) and forward == 3:
            text = (say("Fights for the centre from the side, without committing the central pawns.")
                    if to_file == 2 else
                    say("Gains space on the kingside and eyes the centre, at the cost of loosening the king a little."))
        elif to_file in (1, 6) and forward == 2:
            text = say("Prepares a fianchetto: the bishop will sit on the long diagonal.")
        elif to_file in (0, 7) and forward == 2:
            text = say("A useful waiting move: it takes the {sq} square away from the enemy pieces.",
                       sq=f"{'b' if to_file == 0 else 'g'}{5 if color == chess.WHITE else 4}")
        elif forward == 2 and to_file in (2, 3, 4):
            text = say("A solid move: it supports the centre and opens a diagonal for a bishop.")
        elif forward >= 4:
            text = say("Pushes forward to gain space and cramp the opponent.")
        elif target:
            text = say("Challenges the pawn on {sq}.", sq=target_sq)
        else:
            text = say("A pawn move that shapes the structure and prepares the next piece.")
    elif kind == chess.KNIGHT:
        first = from_rank == home_rank
        base = say("Develops the knight toward the centre" if first else "The knight heads for a better square")
        if not first and (move.to_square in CENTRE or (to_rank in (3, 4) and to_file in (2, 3, 4, 5))):
            base = say("The knight takes a strong central square")
        if target:
            text = say("{base}, attacking the {piece} on {sq}.", target_piece, base=base, sq=target_sq)
        else:
            guarded = [sq for sq in after.attacks(move.to_square) if sq in CENTRE
                       and after.piece_at(sq) and after.piece_at(sq).color == color
                       and after.piece_at(sq).piece_type == chess.PAWN]
            text = (say("{base} and protects the pawn on {sq}.", base=base, sq=chess.square_name(guarded[0]))
                    if guarded else say("{base}.", base=base))
    elif kind == chess.BISHOP:
        first = from_rank == home_rank
        pin = _pinned_knight(after, move.to_square, color)
        long_diagonal = to_file in (1, 6) and to_rank in (1, 6)
        if pin:
            text = say("Pins the knight on {sq} to the {piece}: it cannot move freely now.",
                       pin[1], sq=chess.square_name(pin[0]))
        elif long_diagonal:
            text = say("The bishop settles on the long diagonal, where it works across the whole board.")
        elif target:
            text = say("The bishop comes out and attacks the {piece} on {sq}.", target_piece, sq=target_sq)
        elif first and to_file in (2, 5) and to_rank in (3, 4):
            text = say("Develops the bishop to its most active diagonal, looking at {sq}.",
                       sq="f7" if color == chess.WHITE else "f2")
        elif first:
            text = say("Develops the bishop and clears the way to castle.")
        else:
            text = say("The bishop moves to a safer or more useful diagonal.")
    elif kind == chess.QUEEN:
        if target:
            text = say("The queen comes out with a threat on the {piece} on {sq}.", target_piece, sq=target_sq)
        elif board.fullmove_number <= 6:
            text = say("The queen comes out early. It is active here, but make sure it cannot be chased around.")
        else:
            text = say("Brings the queen to a more active square.")
    elif kind == chess.ROOK:
        pawns = [sq for sq in chess.SquareSet(chess.BB_FILES[to_file])
                 if after.piece_at(sq) and after.piece_at(sq).piece_type == chess.PAWN]
        own = [sq for sq in pawns if after.piece_at(sq).color == color]
        if not pawns:
            text = say("The rook takes the open file.")
        elif not own:
            text = say("The rook goes to the half-open file, where it presses on the enemy pawn.")
        else:
            text = say("The rook moves toward the centre, behind the pawns it will support.")
    else:
        text = say("The king steps aside.")

    if after.is_checkmate():
        text += say(" Checkmate!")
    elif after.is_check() and not board.is_castling(move):
        text += say(" With check.")
    return text


# --------------------------------------------------------------------------
# Building lines
# --------------------------------------------------------------------------
def _play(pairs, lang="en"):
    """[(san, comment)] -> list of plies with fen/uci; comments are generated when empty."""
    board = chess.Board()
    plies = []
    for san, comment in pairs:
        move = board.parse_san(san)                 # raises ValueError on an illegal move
        text = comment or explain_move(board, move, lang)
        number = board.fullmove_number
        color = "w" if board.turn == chess.WHITE else "b"
        board.push(move)
        plies.append({"san": san, "uci": move.uci(), "comment": text, "color": color,
                      "move_number": number, "fen": board.fen()})
    return plies


def _lines(lesson):
    """Main line + variations of a hand-written lesson, each as a full list of plies."""
    lines = [{"name": "Main line", "start": 0, "plies": _play(lesson["line"])}]
    for variation in lesson.get("variations", []):
        pairs = lesson["line"][: variation["start"]] + variation["moves"]
        lines.append({"name": variation["name"], "start": variation["start"], "plies": _play(pairs)})
    return lines


def _spanish(lesson):
    """The lesson with its Spanish text (lessons_es.py); untranslated parts stay in English."""
    from analysis.lessons_es import LESSONS_ES
    es = LESSONS_ES.get(lesson["id"])
    if not es:
        return dict(lesson)
    item = dict(lesson)
    for key in ("name", "tags", "tagline", "why", "ideas", "watch"):
        item[key] = es.get(key) or lesson[key]
    item["line"] = [(san, text) for (san, _), text in zip(lesson["line"], es["line"])]
    item["variations"] = [
        {"name": tr["name"], "start": variation["start"],
         "moves": [(san, text) for (san, _), text in zip(variation["moves"], tr["moves"])]}
        for variation, tr in zip(lesson.get("variations", []), es.get("variations", []))]
    return item


@lru_cache(maxsize=2)
def _lessons(lang="en"):
    """Lessons by id in ``lang``, with their signature as tuples of SAN."""
    out = {}
    for lesson in LESSONS:
        item = _spanish(lesson) if lang == "es" else dict(lesson)
        item["name_en"] = lesson["name"]
        item["sig_moves"] = [tuple(sig.split()) for sig in lesson["sigs"]]
        out[lesson["id"]] = item
    return out


def _starts_with(sans, sig):
    return len(sans) >= len(sig) and tuple(sans[: len(sig)]) == sig


def _matches(lesson, sans):
    return any(_starts_with(sans, sig) for sig in lesson["sig_moves"])


def _signature_fen(lesson):
    """Position after the moves that define the opening (for the card's mini board)."""
    board = chess.Board()
    for san in lesson["sig_moves"][0]:
        board.push_san(san)
    return board.fen()


# --------------------------------------------------------------------------
# The whole database of named openings (Lichess TSVs)
# --------------------------------------------------------------------------
_db = None
_db_lock = threading.Lock()


def database():
    """Every named opening: [{"id", "eco", "name", "sans"}], in file order."""
    global _db
    with _db_lock:
        if _db is None:
            rows = []
            for tsv in sorted(config.OPENINGS_DIR.glob("*.tsv")):
                with open(tsv, newline="", encoding="utf-8") as handle:
                    for row in csv.DictReader(handle, delimiter="\t"):
                        sans = tuple(t for t in row["pgn"].split() if not t[0].isdigit())
                        rows.append({"id": f"db-{len(rows)}", "eco": row["eco"],
                                     "name": row["name"], "sans": sans})
            _db = rows
        return _db


def _db_item(entry):
    return {"id": entry["id"], "eco": entry["eco"], "name": entry["name"],
            "moves": _numbered(entry["sans"]), "plies": len(entry["sans"])}


def _numbered(sans):
    out = []
    for i, san in enumerate(sans):
        out.append(f"{i // 2 + 1}.{san}" if i % 2 == 0 else san)
    return " ".join(out)


def search(query, limit=40):
    """Named openings whose name, ECO code or moves contain every word of ``query``."""
    words = [w for w in (query or "").lower().replace(",", " ").split() if w]
    if not words:
        return []
    found = []
    for entry in database():
        hay = f"{entry['name']} {entry['eco']} {_numbered(entry['sans'])}".lower()
        if all(word in hay for word in words):
            found.append(entry)
    # shorter lines first: "Italian Game" before its fifteenth sub-variation
    found.sort(key=lambda e: (len(e["sans"]), e["name"]))
    return [_db_item(e) for e in found[:limit]]


def _named_variations(sigs, limit=40):
    """Database openings that continue one of the given move sequences."""
    found = [e for e in database()
             if any(len(e["sans"]) > len(sig) and e["sans"][: len(sig)] == sig for sig in sigs)]
    found.sort(key=lambda e: (len(e["sans"]), e["name"]))
    return [_db_item(e) for e in found[:limit]]


# --------------------------------------------------------------------------
# The user's own games
# --------------------------------------------------------------------------
_moves_cache = {}


def _game_sans(row):
    """First plies of a stored game in SAN (cached by game id)."""
    if row["id"] not in _moves_cache:
        sans = []
        try:
            game = chess.pgn.read_game(io.StringIO(row["pgn"]))
            if game is not None and "FEN" not in game.headers:
                board = game.board()
                for move in game.mainline_moves():
                    sans.append(board.san(move))
                    board.push(move)
                    if len(sans) >= GAME_PLIES:
                        break
        except (ValueError, AssertionError):
            sans = []
        _moves_cache[row["id"]] = tuple(sans)
    return _moves_cache[row["id"]]


def _outcome(result, hero):
    if result == "1/2-1/2":
        return "draw"
    if result in ("1-0", "0-1"):
        return "win" if (result == "1-0") == (hero == "w") else "loss"
    return "other"


def _user_games(username):
    """[{id, sans, hero, outcome, opponent, date}] for the user's stored games, newest first."""
    games = []
    if not username:
        return games
    for row in store.games_for_user(username):
        meta = row["meta"]
        hero = meta.get("hero")
        sans = _game_sans(row)
        if hero not in ("w", "b") or len(sans) < 2:
            continue
        opponent = meta.get("black" if hero == "w" else "white") or {}
        me = meta.get("white" if hero == "w" else "black") or {}
        games.append({"id": row["id"], "sans": sans, "hero": hero,
                      "outcome": meta.get("outcome") or _outcome(meta.get("result"), hero),
                      "date": meta.get("date"),
                      "opponent": opponent.get("name"), "opponent_rating": opponent.get("rating"),
                      "rating": me.get("rating")})
    return games


def _tally(games):
    out = {"games": len(games), "win": 0, "draw": 0, "loss": 0, "score": None}
    for game in games:
        if game["outcome"] in ("win", "draw", "loss"):
            out[game["outcome"]] += 1
    decided = out["win"] + out["draw"] + out["loss"]
    if decided:
        out["score"] = round(100 * (out["win"] + 0.5 * out["draw"]) / decided)
    return out


def _top(counter):
    """Most common key of a {key: count} dict and its share (0..100)."""
    total = sum(counter.values())
    if not total:
        return None, 0
    key = max(counter, key=counter.get)
    return key, round(100 * counter[key] / total)


def profile(games):
    """What the user actually plays: first move as White, replies to 1.e4 / 1.d4 as Black."""
    white, vs_e4, vs_d4 = {}, {}, {}
    for game in games:
        first, reply = game["sans"][0], game["sans"][1]
        if game["hero"] == "w":
            white[first] = white.get(first, 0) + 1
        elif first == "e4":
            vs_e4[reply] = vs_e4.get(reply, 0) + 1
        elif first == "d4":
            vs_d4[reply] = vs_d4.get(reply, 0) + 1
    rating = next((g["rating"] for g in games if g["rating"]), None)
    out = {"games": len(games), "rating": rating, "white": {}, "vs_e4": {}, "vs_d4": {}}
    for key, counter in (("white", white), ("vs_e4", vs_e4), ("vs_d4", vs_d4)):
        move, share = _top(counter)
        out[key] = {"move": move, "share": share, "games": sum(counter.values())}
    return out


def _fit(lesson, plays, faces, prof):
    """Score how well a lesson suits the user, with the reasons in plain words."""
    score, reasons, needs_work = lesson["popularity"] * 2, [], False
    side = "White" if lesson["side"] == "w" else "Black"
    if plays["games"]:
        score += min(40, 12 + plays["games"] * 3)
        times = "once" if plays["games"] == 1 else f"{plays['games']} times"
        reasons.append(f"You have played it {times} as {side}"
                       + (f" · you score {plays['score']}%" if plays["score"] is not None else ""))
        if plays["games"] >= 3 and plays["score"] is not None and plays["score"] < 40:
            score += 10
            needs_work = True
            reasons.append("Your results here can improve a lot")
    if faces["games"] >= 2:
        score += min(20, faces["games"] * 2)
        other = "Black" if lesson["side"] == "w" else "White"
        reasons.append(f"You face it often as {other} ({faces['games']} games"
                       + (f", you score {faces['score']}%)" if faces["score"] is not None else ")"))
    # Does it start the way the user already starts?
    first, reply = lesson["line"][0][0], lesson["line"][1][0]
    if lesson["side"] == "w" and prof["white"]["move"] == first and prof["white"]["games"] >= 3:
        score += 20
        reasons.append(f"Starts with 1.{first}, your usual first move")
    elif lesson["family"] in ("vs_e4", "vs_d4"):
        mine = prof[lesson["family"]]
        if mine["move"] == reply and mine["games"] >= 3:
            score += 20
            reasons.append(f"You already answer 1.{first} with 1...{reply}")
    rating = prof["rating"]
    if rating is not None and rating < 1000:
        if lesson["level"] == 1:
            score += 15
            reasons.append("Simple plans: ideal at your level")
        elif lesson["level"] == 3:
            score -= 12
    elif rating is not None and rating < 1500 and lesson["level"] == 1:
        score += 6
    return score, reasons, needs_work


def _card(lesson):
    return {"id": lesson["id"], "name": lesson["name"], "name_en": lesson["name_en"], "eco": lesson["eco"], "side": lesson["side"],
            "family": lesson["family"], "family_name": FAMILY_NAMES[lesson["family"]],
            "level": lesson["level"], "level_name": LEVEL_NAMES[lesson["level"]],
            "popularity": lesson["popularity"], "tags": lesson["tags"], "tagline": lesson["tagline"],
            "fen": _signature_fen(lesson), "moves": _numbered(lesson["sig_moves"][0])}


def _split(lesson, games):
    """Games where the user played this opening / had it played against them."""
    plays = [g for g in games if _matches(lesson, g["sans"]) and g["hero"] == lesson["side"]]
    faces = [g for g in games if _matches(lesson, g["sans"]) and g["hero"] != lesson["side"]]
    return plays, faces


def overview(username, lang="en"):
    """Everything the Openings page needs: lesson cards with the user's numbers and fit."""
    games = _user_games(username)
    prof = profile(games)
    cards = []
    for lesson in _lessons(lang).values():
        plays, faces = _split(lesson, games)
        card = _card(lesson)
        card["plays"], card["faces"] = _tally(plays), _tally(faces)
        card["fit"], card["reasons"], card["needs_work"] = _fit(lesson, card["plays"], card["faces"], prof)
        cards.append(card)
    return {"username": username, "profile": prof, "lessons": cards,
            "database_size": len(database())}


def _recent(games, limit=6):
    return [{k: g[k] for k in ("id", "outcome", "date", "opponent", "opponent_rating")}
            for g in games[:limit]]


def lesson_detail(lesson_id, username=None, lang="en"):
    """Full lesson for the board: lines with a position and a coach comment per move.

    ``lesson_id`` is a hand-written lesson id or ``db-<n>`` for any named opening
    of the database (explained automatically). Returns None when unknown.
    """
    games = _user_games(username)
    lessons = _lessons(lang)
    if lesson_id in lessons:
        lesson = lessons[lesson_id]
        plays, faces = _split(lesson, games)
        detail = _card(lesson)
        detail.update({
            "curated": True, "why": lesson["why"], "ideas": lesson["ideas"], "watch": lesson["watch"],
            "lines": _lines(lesson), "signature_plies": len(lesson["sig_moves"][0]),
            "plays": _tally(plays), "faces": _tally(faces),
            "recent": {"plays": _recent(plays), "faces": _recent(faces)},
            "named": _named_variations(lesson["sig_moves"]),
        })
        return detail

    entry = next((e for e in database() if e["id"] == lesson_id), None)
    if entry is None:
        return None
    try:
        plies = _play([(san, "") for san in entry["sans"]], lang)
    except ValueError:
        return None
    # Guess whose opening it is from its name; the lesson it belongs to, if any
    lowered = entry["name"].lower()
    side = "b" if any(word in lowered for word in ("defense", "defence", "counter", "indian")) \
        and "attack" not in lowered else "w"
    parent = None
    for lesson in lessons.values():
        if _matches(lesson, entry["sans"]):
            if parent is None or len(lesson["sig_moves"][0]) > len(parent["sig_moves"][0]):
                parent = lesson
    played = [g for g in games if _starts_with(g["sans"], entry["sans"])]
    plays = [g for g in played if g["hero"] == side]
    faces = [g for g in played if g["hero"] != side]
    return {
        "id": entry["id"], "name": entry["name"], "eco": entry["eco"], "side": side,
        "curated": False, "family_name": "Opening database", "level_name": None, "tags": [],
        "tagline": _numbered(entry["sans"]), "fen": plies[-1]["fen"] if plies else chess.STARTING_FEN,
        "why": None, "ideas": [], "watch": None,
        "lines": [{"name": "Moves", "start": 0, "plies": plies}],
        "signature_plies": len(plies),
        "plays": _tally(plays), "faces": _tally(faces),
        "recent": {"plays": _recent(plays), "faces": _recent(faces)},
        "named": _named_variations([entry["sans"]]),
        "parent": {"id": parent["id"], "name": parent["name"]} if parent else None,
    }

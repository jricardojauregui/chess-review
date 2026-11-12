"""Move classification (Brilliant ... Blunder), accuracy and context tags.

Works on plain engine output (see ``engine.analyse_line``): for a game with N
moves it needs the N+1 analysed positions. All thresholds come from config.py.
"""
import math

import chess

import config
from analysis.engine import line_win

# Classification labels
BOOK, FORCED, BRILLIANT, GREAT, MISS, BEST = "book", "forced", "brilliant", "great", "miss", "best"
EXCELLENT, GOOD, INACCURACY, MISTAKE, BLUNDER = "excellent", "good", "inaccuracy", "mistake", "blunder"
ALL_LABELS = [BRILLIANT, GREAT, BEST, EXCELLENT, GOOD, BOOK, INACCURACY, MISTAKE, MISS, BLUNDER, FORCED]

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
                chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}
PIECE_NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
               chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king"}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def accuracy_from_loss(loss):
    """Per-move accuracy (0..100) from the win% lost."""
    value = config.ACC_A * math.exp(-config.ACC_B * loss) - config.ACC_C
    return max(0.0, min(100.0, value))


def material(board, color, pawns=True):
    """Material points of one side (optionally without pawns)."""
    total = 0
    for piece_type, value in PIECE_VALUES.items():
        if piece_type == chess.PAWN and not pawns:
            continue
        total += value * len(board.pieces(piece_type, color))
    return total


def balance(board, color):
    """Material balance from ``color``'s point of view."""
    return material(board, color) - material(board, not color)


def capture_value(board, move):
    """Points gained immediately by ``move`` (captured piece + promotion bonus)."""
    value = 0
    if board.is_en_passant(move):
        value += 1
    elif board.is_capture(move):
        value += PIECE_VALUES[board.piece_type_at(move.to_square)]
    if move.promotion:
        value += PIECE_VALUES[move.promotion] - 1
    return value


def see_capture(board, move):
    """Static Exchange Evaluation of a capture, in points for the capturing side.

    Plays the capture and lets the other side recapture on the same square with
    whichever legal recapture is best for them (recursively).
    """
    gain = capture_value(board, move)
    after = board.copy(stack=False)
    after.push(move)
    best_reply = 0
    for reply in after.legal_moves:
        if reply.to_square == move.to_square and after.is_capture(reply):
            best_reply = max(best_reply, see_capture(after, reply))
    return gain - best_reply


def hanging_pieces(board, color):
    """Pieces of ``color`` the side to move can win by SEE.

    ``board`` must have the opponent of ``color`` to move. Returns a list of
    ``{"square", "piece_type", "gain"}`` (best gain per target square).
    """
    found = {}
    for move in board.legal_moves:
        if not board.is_capture(move) or board.is_en_passant(move):
            continue
        target = board.piece_at(move.to_square)
        if target is None or target.color != color:
            continue
        gain = see_capture(board, move)
        if gain > 0 and gain > found.get(move.to_square, {}).get("gain", 0):
            found[move.to_square] = {"square": move.to_square,
                                     "piece_type": target.piece_type, "gain": gain}
    return list(found.values())


def _track(board, pv_uci, color):
    """Boards' (balance, non-pawn material of ``color``) along a PV.

    Index 0 is ``board`` itself, index k the position after k PV plies.
    """
    walker = board.copy(stack=False)
    track = [(balance(walker, color), material(walker, color, pawns=False))]
    for uci in pv_uci:
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            break
        if move not in walker.legal_moves:
            break
        walker.push(move)
        track.append((balance(walker, color), material(walker, color, pawns=False)))
    return track


def _offered_material(after, mover):
    """Points the opponent can really win by taking one of ``mover``'s pieces.

    SEE alone only looks at one square, so it would call a discovered attack
    or a desperado a "sacrifice" (take my knight, I take your queen). For each
    winning capture we therefore also let the mover answer with their best
    capture anywhere on the board, and only count what is left.
    """
    offered = 0
    for capture in after.legal_moves:
        if not after.is_capture(capture) or after.is_en_passant(capture):
            continue
        target = after.piece_at(capture.to_square)
        if target is None or target.color != mover:
            continue
        value = PIECE_VALUES[target.piece_type]
        if value < config.SACRIFICE_MIN_PIECE_VALUE:
            continue
        gain = see_capture(after, capture)
        if gain <= offered:
            continue
        taken = after.copy(stack=False)
        taken.push(capture)
        regain = max((see_capture(taken, m) for m in taken.legal_moves if taken.is_capture(m)),
                     default=0)
        offered = max(offered, min(gain, value - max(regain, 0)))
    return offered


def _is_en_prise(board, square):
    """True when the opponent could win material by capturing on ``square`` if
    it were their move (i.e. the piece standing there is under real attack)."""
    probe = board.copy(stack=False)
    probe.turn = not board.turn
    probe.ep_square = None
    for capture in probe.generate_pseudo_legal_captures():
        if capture.to_square == square and probe.is_legal(capture):
            if see_capture(probe, capture) > 0:
                return True
    return False


def is_sacrifice(board, move, pv_after):
    """True when ``move`` is a real (non-pawn) material sacrifice.

    Either the move leaves a piece en prise according to SEE (net of whatever
    the move itself captured), or the engine's line shows the mover down
    material after their own follow-up moves within the next few plies.
    """
    mover = board.turn
    grabbed = capture_value(board, move)
    before_balance = balance(board, mover)
    before_heavy = material(board, mover, pawns=False)
    after = board.copy(stack=False)
    after.push(move)

    # A) a piece is left hanging
    if _offered_material(after, mover) - grabbed >= config.SACRIFICE_MIN_POINTS:
        return True

    # B) the PV shows the material actually being given up. Only look at
    # positions after the mover's own replies (even plies) so that ordinary
    # capture/recapture sequences are not mistaken for sacrifices.
    track = _track(after, pv_after[: config.SACRIFICE_PV_PLIES], mover)
    for k in range(2, len(track), 2):
        bal, heavy = track[k]
        if (before_balance - bal >= config.SACRIFICE_MIN_POINTS
                and before_heavy - heavy >= config.SACRIFICE_MIN_PIECE_VALUE):
            return True
    return False


def move_ideas(after, move):
    """The main idea of a move, as arrows for the review board (orange, as in
    chess.com's Game Review): enemy pieces the moved piece now attacks and
    could profitably take (worth more than it, or undefended), and checks.
    Returns up to three ``{"orig", "dest", "kind"}`` (kind: "check" | "threat").
    """
    mover = not after.turn
    square = move.to_square
    piece = after.piece_at(square)
    if piece is None:
        return []
    ideas = []
    for target in after.attacks(square):
        victim = after.piece_at(target)
        if victim is None or victim.color == mover:
            continue
        if victim.piece_type == chess.KING:
            ideas.append((100, "check", target))
        elif (PIECE_VALUES[victim.piece_type] > PIECE_VALUES[piece.piece_type]
              or not after.is_attacked_by(not mover, target)):
            ideas.append((PIECE_VALUES[victim.piece_type], "threat", target))
    ideas.sort(reverse=True)
    return [{"orig": chess.square_name(square), "dest": chess.square_name(t), "kind": kind}
            for _, kind, t in ideas[:3]]


def material_gain(board_after, pv_after, mover, baseline):
    """Material ``mover`` ends up ahead of ``baseline`` once the PV settles.

    Checks the position after the opponent's replies (odd plies), i.e. once
    they have had the chance to recapture.
    """
    track = _track(board_after, pv_after[:3], mover)
    settled = [track[k][0] for k in range(1, len(track), 2)]
    if not settled:
        return 0
    return settled[-1] - baseline


def material_phrase(points):
    """Human wording for a material swing."""
    return {1: "a pawn", 2: "material", 3: "a piece", 5: "a rook",
            9: "a queen"}.get(points, "the queen" if points > 9 else "material")


def game_phase(board, ply):
    """"opening" / "middlegame" / "endgame" for a position (Lichess-style)."""
    pieces = sum(len(board.pieces(pt, c)) for c in chess.COLORS
                 for pt in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN))
    if pieces <= config.ENDGAME_MAX_PIECES:
        return "endgame"
    back_white = chess.popcount(board.occupied_co[chess.WHITE] & chess.BB_RANK_1)
    back_black = chess.popcount(board.occupied_co[chess.BLACK] & chess.BB_RANK_8)
    if (pieces <= config.MIDDLEGAME_MAX_PIECES or back_white < 4 or back_black < 4
            or ply > config.OPENING_MAX_PLY):
        return "middlegame"
    return "opening"


def _white_eval(cp, mate, pov_is_white):
    """Convert a (cp, mate) pair to White's point of view plus display text."""
    sign = 1 if pov_is_white else -1
    if mate is not None:
        mate *= sign
        return {"cp": None, "mate": mate, "text": ("+" if mate > 0 else "-") + f"M{abs(mate)}"}
    cp = (cp or 0) * sign
    return {"cp": cp, "mate": None, "text": f"{cp / 100:+.2f}"}


def _line_view(line, pov_is_white):
    """Public shape of an engine line, with eval from White's POV."""
    return {"uci": line["uci"], "san": line["san"], "pv": line["pv"],
            "pv_san": line["pv_san"],
            "eval": _white_eval(line["cp"], line["mate"], pov_is_white)}


def _ladder(loss):
    if loss < config.EXCELLENT_MAX:
        return EXCELLENT
    if loss < config.GOOD_MAX:
        return GOOD
    if loss < config.INACCURACY_MAX:
        return INACCURACY
    if loss < config.MISTAKE_MAX:
        return MISTAKE
    return BLUNDER


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------
def classify_game(start_board, moves, positions, book_plies=0, opening_names=None):
    """Classify every move of a game.

    ``positions`` is the engine output for the N+1 positions. Returns one dict
    per move (see the keys built at the end of the loop).
    """
    opening_names = opening_names or []
    board = start_board.copy()
    results = []
    prev = None
    balance_two_plies_ago = balance(board, chess.WHITE)   # White POV
    phase_rank = {"opening": 0, "middlegame": 1, "endgame": 2}
    phase = "opening"

    for index, move in enumerate(moves):
        pos, nxt = positions[index], positions[index + 1]
        mover = board.turn
        white = mover == chess.WHITE
        lines = pos.get("lines") or []
        best = lines[0] if lines else None
        second = lines[1] if len(lines) > 1 else None
        san = board.san(move)
        after = board.copy(stack=False)
        after.push(move)

        # ---- win% before / after, loss ------------------------------------
        win_best = line_win(best) if best else 50.0
        if nxt["terminal"] == "checkmate":
            win_after, eval_after = 100.0, {"cp": None, "mate": 0, "text": "#"}
            next_best = None
        elif nxt["terminal"] == "draw" or not nxt.get("lines"):
            win_after, eval_after = 50.0, {"cp": 0, "mate": None, "text": "0.00"}
            next_best = None
        else:
            next_best = nxt["lines"][0]                     # opponent's POV
            win_after = 100.0 - line_win(next_best)
            eval_after = _white_eval(next_best["cp"], next_best["mate"], not white)
        is_best = bool(best and move.uci() == best["uci"]) or nxt["terminal"] == "checkmate"
        loss = 0.0 if is_best else max(0.0, win_best - win_after)
        pv_after = next_best["pv"] if next_best else []

        # ---- facts used by rules and tags ---------------------------------
        own_baseline = balance_two_plies_ago if white else -balance_two_plies_ago
        sacrifice = is_sacrifice(board, move, pv_after)
        gain_played = material_gain(after, pv_after, mover, own_baseline)
        gain_best = 0
        if best and not is_best:
            best_move = chess.Move.from_uci(best["uci"])
            best_after = board.copy(stack=False)
            best_after.push(best_move)
            gain_best = material_gain(best_after, best["pv"][1:], mover, own_baseline)
        had_mate = best["mate"] if best and best["mate"] and best["mate"] > 0 else None
        still_mating = (nxt["terminal"] == "checkmate"
                        or bool(next_best and next_best["mate"] is not None and next_best["mate"] < 0))
        missed_mate = had_mate if had_mate and not still_mating else None
        allows_mate = (next_best["mate"] if next_best and next_best["mate"] and next_best["mate"] > 0
                       else None)
        opp_erred = prev is not None and prev["cls"] in (MISTAKE, BLUNDER)
        is_recapture = bool(prev and prev["capture"] and board.is_capture(move)
                            and move.to_square == chess.parse_square(prev["uci"][2:4]))
        gap = (win_best - line_win(second)) if second else None
        gives_mate = nxt["terminal"] == "checkmate"
        # "Obvious" moves: recapture, mate in one, or stepping an attacked piece away.
        simple_retreat = (not board.is_capture(move) and not after.is_check()
                          and _is_en_prise(board, move.from_square))
        obvious = is_recapture or gives_mate or simple_retreat
        grabbed = capture_value(board, move)

        # ---- classification rules, in order --------------------------------
        reason = None
        if index < book_plies:
            cls = BOOK
        elif pos["legal_count"] == 1:
            cls = FORCED
        elif ((is_best or loss <= config.BRILLIANT_MAX_LOSS) and sacrifice
              and win_best <= config.BRILLIANT_MAX_WIN_BEFORE
              and win_after >= config.BRILLIANT_MIN_WIN_AFTER):
            cls = BRILLIANT
        elif (is_best and gap is not None and gap >= config.GREAT_MIN_GAP
              and win_best >= config.GREAT_MIN_WIN_BEST
              and win_best - gap <= config.GREAT_MAX_WIN_SECOND
              and not (config.GREAT_SKIP_OBVIOUS and obvious)):
            # Critical to the outcome: the only move that keeps (or wins) the game.
            cls, reason = GREAT, ("refutes" if opp_erred else "only_move")
        elif (opp_erred and prev["loss"] >= config.MISS_MIN_OPPORTUNITY
              and loss >= config.MISS_MIN_LOSS):
            cls = MISS
        elif (missed_mate and missed_mate <= config.MISSED_MATE_MAX_N
              and loss < config.INACCURACY_MAX):
            cls = MISS
        elif is_best:
            cls = BEST
        else:
            cls = _ladder(loss)

        # ---- context tags for the coach ------------------------------------
        tags = []
        info = {"piece": PIECE_NAMES[board.piece_type_at(move.from_square)]}
        if reason:
            tags.append(reason)
        if board.is_capture(move):
            tags.append("capture")
            captured = (chess.PAWN if board.is_en_passant(move)
                        else board.piece_type_at(move.to_square))
            info["captured"] = PIECE_NAMES[captured]
        if is_recapture:
            tags.append("recapture")
        if after.is_checkmate():
            tags.append("checkmate")
        elif after.is_check():
            tags.append("check")
        if board.is_castling(move):
            tags.append("castle")
        if move.promotion:
            tags.append("promotion")
            info["promoted"] = PIECE_NAMES[move.promotion]
        if sacrifice:
            tags.append("sacrifice")
        if still_mating and not after.is_checkmate():
            tags.append("mate_found")
            info["mate_n"] = abs(next_best["mate"])
        if missed_mate:
            tags.append("missed_mate")
            info["missed_mate_n"] = missed_mate
        if allows_mate:
            tags.append("allows_mate")
            info["allows_mate_n"] = allows_mate
        mate_on_board = still_mating or bool(allows_mate)   # material is irrelevant then
        if (gain_played >= config.TACTIC_MIN_POINTS and loss < config.INACCURACY_MAX
                and not mate_on_board):
            tags.append("tactic")
            info["material"] = material_phrase(gain_played)
        if (not is_best and gain_best >= config.TACTIC_MIN_POINTS and not had_mate
                and gain_best - gain_played >= config.TACTIC_MIN_POINTS):
            tags.append("missed_tactic")
            info["best_material"] = material_phrase(gain_best)
        # Hanging piece: the opponent's best reply simply wins something.
        if next_best and loss >= config.GOOD_MAX:
            reply = chess.Move.from_uci(next_best["uci"])
            if after.is_capture(reply) and not after.is_en_passant(reply):
                hung = after.piece_type_at(reply.to_square)
                # ...beyond whatever this move captured itself (a trade is not a hang)
                if hung != chess.PAWN and see_capture(after, reply) - grabbed >= 1:
                    tags.append("hangs_piece")
                    info["hung"] = PIECE_NAMES[hung]

        new_phase = game_phase(board, index + 1)
        if phase_rank[new_phase] > phase_rank[phase]:
            phase = new_phase
        if phase == "endgame":
            tags.append("endgame")
        if index < len(opening_names) and opening_names[index]:
            info["opening"] = opening_names[index]

        good_moves = [l["uci"] for l in lines
                      if win_best - line_win(l) <= config.RETRY_TOLERANCE]
        win_white = win_after if white else 100.0 - win_after
        result = {
            "ply": index + 1,
            "move_number": board.fullmove_number,
            "color": "w" if white else "b",
            "san": san,
            "uci": move.uci(),
            "fen_before": board.fen(),
            "fen_after": after.fen(),
            "cls": cls,
            "loss": round(loss, 2),
            "accuracy": round(accuracy_from_loss(loss), 2),
            "is_best": is_best,
            "capture": board.is_capture(move),
            "win_before": round(win_best, 2),      # mover POV, with best play
            "win_after": round(win_after, 2),      # mover POV
            "win_white": round(win_white, 2),      # White POV, after the move
            "eval": eval_after,                    # White POV, after the move
            "best": _line_view(best, white) if best else None,
            "second": _line_view(second, white) if second else None,
            "good_moves": good_moves,
            # Review arrows, following chess.com's colour meanings:
            "ideas": move_ideas(after, move),                       # orange: main idea
            # red: the reply that punishes a bad move
            "punish": (next_best["uci"] if next_best and cls in (MISTAKE, BLUNDER) else None),
            # blue: the opponent's concrete response (a capture), e.g. taking a sacrificed piece
            "reply": (next_best["uci"] if next_best and cls not in (MISTAKE, BLUNDER)
                      and after.is_capture(chess.Move.from_uci(next_best["uci"])) else None),
            "tags": tags,
            "info": info,
            "phase": phase,
        }
        results.append(result)

        balance_two_plies_ago = balance(board, chess.WHITE)
        prev = result
        board.push(move)

    return results


# --------------------------------------------------------------------------
# Game accuracy
# --------------------------------------------------------------------------
def _stdev(values):
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def game_accuracy(results, initial_win_white=50.0, mode=None):
    """Accuracy per player. Returns {"w": x, "b": y} (None for a side without moves).

    mode "mean": plain average of the move accuracies.
    mode "weighted": each move is weighted by the standard deviation of the
    win% in a sliding window around it (critical positions count more), and
    the result is the average of that weighted mean and the harmonic mean.
    This is the one that tracks chess.com's published numbers best.
    """
    mode = mode or config.ACCURACY_MODE
    if not results:
        return {"w": None, "b": None}
    if mode == "mean":
        out = {}
        for color in ("w", "b"):
            accs = [r["accuracy"] for r in results if r["color"] == color]
            out[color] = round(sum(accs) / len(accs), 1) if accs else None
        return out
    wins = [initial_win_white] + [r["win_white"] for r in results]
    size = max(2, min(8, len(results) // 10))
    windows = [wins[:size]] * max(0, min(size, len(wins)) - 2)
    windows += [wins[i:i + size] for i in range(len(wins) - size + 1)]
    weights = [max(0.5, min(12.0, _stdev(w))) for w in windows]

    out = {}
    for color in ("w", "b"):
        pairs = [(r["accuracy"], weights[i] if i < len(weights) else 0.5)
                 for i, r in enumerate(results) if r["color"] == color]
        if not pairs:
            out[color] = None
            continue
        weighted = sum(a * w for a, w in pairs) / sum(w for _, w in pairs)
        harmonic = len(pairs) / sum(1 / max(a, 1.0) for a, _ in pairs)
        out[color] = round((weighted + harmonic) / 2, 1)
    return out

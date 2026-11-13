"""Coach messages: a bank of templates per classification x context.

Templates are written so they work in three "voices":
  * the reviewed player ("You ... your ...")
  * their opponent ("Your opponent ... their ...")
  * neutral, when we do not know who the user is ("White ... White's ...")
Verbs are kept in the past tense so one template fits all three.

Placeholders: {move} {best} {piece} {material} {n} {opening}
              {Subj} {subj} {poss} {Opp} {opp} {opp_poss}
"""
import hashlib

import config
from analysis import coach_es

from analysis import classify as C

# Coach face per classification
EXPRESSIONS = {
    C.BRILLIANT: "surprised", C.GREAT: "surprised",
    C.BEST: "happy", C.EXCELLENT: "happy", C.GOOD: "happy", C.BOOK: "happy",
    C.FORCED: "thinking", C.INACCURACY: "thinking",
    C.MISS: "worried", C.MISTAKE: "worried", C.BLUNDER: "worried",
}

TITLES = {
    C.BRILLIANT: "{move} is brilliant", C.GREAT: "{move} is a great move",
    C.BEST: "{move} is best", C.EXCELLENT: "{move} is excellent",
    C.GOOD: "{move} is good", C.BOOK: "{move} is a book move",
    C.FORCED: "{move} is forced", C.INACCURACY: "{move} is an inaccuracy",
    C.MISTAKE: "{move} is a mistake", C.MISS: "{move} is a miss",
    C.BLUNDER: "{move} is a blunder",
}

# (classification, context) -> variants. Context None is the fallback.
TEMPLATES = {
    # ---------------------------------------------------------------- brilliant
    (C.BRILLIANT, "tactic"): [
        "{Subj} saw {poss} chance for the win with a nice tactic and took it!",
        "Wow! {Subj} gave up material and the tactic works perfectly.",
        "A stunning shot. The sacrifice wins {material} by force.",
        "Now that is calculation! {move} sacrifices, and the follow-up pays it all back.",
        "Brilliant! The {piece} could be taken, but the tactic behind it is crushing.",
    ],
    (C.BRILLIANT, "checkmate"): [
        "A sacrifice that ends in checkmate. It doesn't get prettier than that!",
        "Brilliant! Material didn't matter, only the king did.",
        "{Subj} gave it all up for the mate. Beautiful!",
        "The perfect finish: a sacrifice and the king has nowhere to go.",
    ],
    (C.BRILLIANT, None): [
        "A real sacrifice, and it is completely sound. Brilliant!",
        "Wow! {Subj} offered material and the engine loves it.",
        "That takes courage. {move} gives up material for a lasting initiative.",
        "Not many players would even consider {move}. Superb!",
        "A brilliant idea: the {piece} is offered, and taking it only helps {subj}.",
        "Material isn't everything. {move} proves it.",
    ],
    # -------------------------------------------------------------------- great
    (C.GREAT, "only_move"): [
        "That was the only move that held everything together. Great find!",
        "Everything else was clearly worse. {Subj} found the one good move!",
        "A critical moment, and {subj} got it exactly right.",
        "Great move! Any other choice would have let the position slip.",
        "The only move, and far from obvious. Well spotted!",
    ],
    (C.GREAT, "refutes"): [
        "{Opp} slipped and {subj} punished it immediately. Great move!",
        "That is the refutation! {move} shows why the last move was wrong.",
        "Exactly the right punishment. {Opp} will regret that last move.",
        "{Subj} didn't let the chance go by. Great find!",
        "Sharp! The mistake was there to be exploited, and {move} does it.",
    ],
    (C.GREAT, None): [
        "A great move at a critical moment.",
        "Great find! This was much stronger than the alternatives.",
        "Precise and strong. {move} was the move to find here.",
        "That one was hard to see. Great job!",
    ],
    # --------------------------------------------------------------------- best
    (C.BEST, "checkmate"): [
        "Checkmate! A clean finish.",
        "And that's mate. Well played!",
        "Game over! {move} is checkmate.",
        "The king has no escape. Checkmate!",
    ],
    (C.BEST, "mate_found"): [
        "That's the way! It's forced mate in {n} now.",
        "The most precise path: checkmate in {n} is coming.",
        "{Subj} found the mating sequence. {n} to go!",
        "Perfect. The king can't survive this: mate in {n}.",
    ],
    (C.BEST, "tactic"): [
        "Well spotted! That wins {material}.",
        "Exactly right. This tactic picks up {material}.",
        "The best move, and it wins {material}.",
        "Sharp eyes! {move} wins {material}.",
        "{Subj} took what was on offer. That's {material} in the bag.",
    ],
    (C.BEST, "recapture"): [
        "The right way to recapture.",
        "{Subj} took back, keeping the balance.",
        "A natural recapture, and the best one.",
        "Taking back with the {piece} was the most accurate choice.",
    ],
    (C.BEST, "castle"): [
        "King safety first. Castling was the best move here.",
        "The king is tucked away and the rook joins the game. Best move!",
        "Castling at the right time. Exactly what I would have played.",
        "Safe king, connected rooks. Perfect.",
    ],
    (C.BEST, "promotion"): [
        "A new {piece} joins the board. Best move!",
        "The pawn made it all the way. Well done!",
        "Promotion! That was the most accurate way to do it.",
        "That pawn's journey ends in glory. Best move.",
    ],
    (C.BEST, "capture"): [
        "The best capture on the board.",
        "Taking was right. Exactly what I would have played.",
        "{Subj} took the {captured}, and that was the most accurate move.",
        "A good capture. The engine agrees completely.",
    ],
    (C.BEST, "check"): [
        "A strong check, and the best move in the position.",
        "Check! That was the most precise move here.",
        "Keeping the king busy. Best move!",
        "That check was exactly what the position needed.",
    ],
    (C.BEST, "endgame"): [
        "Precise endgame technique. That was the best move.",
        "Every tempo counts in the endgame, and this was the right one.",
        "Exactly what the position required. Clean technique!",
        "The engine's first choice. Endgames reward this precision.",
    ],
    (C.BEST, None): [
        "Exactly what I would have played.",
        "The best move in the position. Nice!",
        "That's the engine's top choice.",
        "Spot on! {move} was the strongest move.",
        "No improvement possible there. Best move!",
        "Right on target.",
    ],
    # ---------------------------------------------------------------- excellent
    (C.EXCELLENT, "capture"): [
        "A fine capture. Almost as good as the very best move.",
        "Taking the {captured} was an excellent choice.",
        "Excellent! That capture keeps everything under control.",
        "Strong and simple. The engine barely prefers anything else.",
    ],
    (C.EXCELLENT, "endgame"): [
        "Excellent technique. The endgame is in good hands.",
        "Very accurate. That keeps the endgame on track.",
        "Nothing wrong with that. A fine endgame move.",
        "An excellent practical choice in the endgame.",
    ],
    (C.EXCELLENT, None): [
        "An excellent move. Just a hair behind the engine's first choice.",
        "Very strong! {best} was marginally better, but this is great.",
        "Excellent. The position stays right where {subj} wanted it.",
        "That's a very accurate move.",
        "Nearly perfect. Nothing to complain about here.",
    ],
    # --------------------------------------------------------------------- good
    (C.GOOD, None): [
        "A good, solid move.",
        "That's fine. {best} was a little more accurate.",
        "Good move. There was something slightly better in {best}.",
        "Reasonable! It keeps the position healthy.",
        "A decent choice, though {best} asked a bit more of the position.",
    ],
    # --------------------------------------------------------------------- book
    (C.BOOK, "opening"): [
        "{opening}. Still in theory, nice and solid.",
        "This is the {opening}. A well-known path.",
        "Book move. We're in the {opening}.",
        "{opening}. Nothing new yet, both sides know their theory.",
        "Straight out of the book: the {opening}.",
    ],
    (C.BOOK, None): [
        "A standard opening move.",
        "Still following opening theory.",
        "Book move. Nothing to add yet.",
        "Known theory. On we go.",
    ],
    # ------------------------------------------------------------------- forced
    (C.FORCED, None): [
        "The only legal move, so no choice there.",
        "Forced. There was nothing else to play.",
        "No decision to make here: it was the only move.",
        "Only one legal move in the position.",
    ],
    # --------------------------------------------------------------- inaccuracy
    (C.INACCURACY, "missed_tactic"): [
        "Not bad, but {best} would have won {material}.",
        "A little imprecise. There was {material} to win with {best}.",
        "This lets a chance slip: {best} picked up {material}.",
        "Playable, though {best} was a concrete improvement.",
    ],
    (C.INACCURACY, None): [
        "A bit imprecise. {best} was the better try.",
        "Not the most accurate. {best} kept more of the advantage.",
        "This gives away a little. Consider {best} instead.",
        "An inaccuracy. {best} would have been stronger.",
        "Slightly off target. {best} was the move.",
    ],
    # ------------------------------------------------------------------ mistake
    (C.MISTAKE, "allows_mate"): [
        "Careful! This allows a forced checkmate in {n}.",
        "That walks into a mating net: mate in {n}. {best} avoided it.",
        "A mistake. The king is now in serious danger: mate in {n}.",
        "This lets {opp} force mate in {n}. {best} was necessary.",
    ],
    (C.MISTAKE, "missed_mate"): [
        "There was a checkmate in {n} here! Look for {best}.",
        "A forced mate in {n} was available, starting with {best}.",
        "The king was ready to be mated in {n}. {best} was the move.",
        "Missed it! {best} led to checkmate in {n}.",
    ],
    (C.MISTAKE, "hangs_piece"): [
        "That leaves {poss} {piece} in trouble. {best} was safer.",
        "A mistake: the {piece} can simply be taken. {best} was better.",
        "The {piece} is not safe after this. {best} kept everything protected.",
        "This drops the {piece}. {best} would have held the position together.",
    ],
    (C.MISTAKE, "missed_tactic"): [
        "A mistake. {best} would have won {material}.",
        "That misses a chance: {best} picked up {material}.",
        "There was {material} to win here with {best}.",
        "The stronger {best} won {material}. This lets it go.",
    ],
    (C.MISTAKE, None): [
        "That's a mistake. {best} was clearly better.",
        "This hands over a good part of the advantage. {best} was the move.",
        "Not the right idea. {best} would have kept things under control.",
        "A mistake. Take another look at {best}.",
        "This makes life harder. {best} was the way to go.",
    ],
    # --------------------------------------------------------------------- miss
    (C.MISS, "missed_mate"): [
        "There was a checkmate in {n} here! Look for {best}.",
        "A missed chance: {best} forced mate in {n}.",
        "The game could have ended here. {best} was mate in {n}!",
        "So close! {best} would have started a forced mate in {n}.",
    ],
    (C.MISS, "missed_tactic"): [
        "{Opp} slipped, but {best} would have punished it, winning {material}.",
        "A missed chance! {best} won {material}.",
        "The last move was an error, and {best} picked up {material}.",
        "There was {material} for the taking with {best}.",
    ],
    (C.MISS, None): [
        "{Opp} slipped, but {best} would have punished it.",
        "A missed opportunity. {best} took full advantage of the last move.",
        "The last move was a mistake, and {best} was the way to exploit it.",
        "That lets {opp} off the hook. {best} was much stronger.",
        "The chance was there! {best} would have changed the game.",
    ],
    # ------------------------------------------------------------------ blunder
    (C.BLUNDER, "allows_mate"): [
        "Oh no! This allows checkmate in {n}.",
        "A blunder: {opp} now has a forced mate in {n}. {best} was essential.",
        "That loses on the spot. It's mate in {n} for {opp}.",
        "The king can't survive this: mate in {n}. {best} held on.",
    ],
    (C.BLUNDER, "missed_mate"): [
        "There was a checkmate in {n} here! Look for {best}.",
        "A blunder: {best} was mate in {n}, and now the win is gone.",
        "The mate in {n} was right there with {best}.",
        "Ouch. {best} forced checkmate in {n}, and this throws it away.",
    ],
    (C.BLUNDER, "hangs_piece"): [
        "Ouch! That leaves {poss} {piece} hanging. {best} was safer.",
        "A blunder: the {piece} is simply lost now. {best} was much better.",
        "That hangs the {piece}. {best} would have kept it safe.",
        "The {piece} is left undefended. {best} was the move.",
        "Oh no, the {piece}! {best} would have avoided all of this.",
    ],
    (C.BLUNDER, "missed_tactic"): [
        "A blunder. {best} would have won {material} instead.",
        "This throws away a big chance: {best} won {material}.",
        "{best} picked up {material}. After this, the tables turn.",
        "Ouch. There was {material} to win with {best}.",
    ],
    (C.BLUNDER, None): [
        "Ouch, that's a blunder. {best} was necessary.",
        "This changes the game. {best} was far better.",
        "A serious error. {best} would have kept the position alive.",
        "That gives the game away. The right move was {best}.",
        "A blunder. Compare it with {best} and the difference is huge.",
    ],
}

# Order in which contexts are tried for each classification
CONTEXT_PRIORITY = {
    C.BRILLIANT: ["checkmate", "tactic"],
    C.GREAT: ["refutes", "only_move"],
    C.BEST: ["checkmate", "mate_found", "tactic", "recapture", "castle",
             "promotion", "capture", "check", "endgame"],
    C.EXCELLENT: ["capture", "endgame"],
    C.BOOK: ["opening"],
    C.INACCURACY: ["missed_tactic"],
    C.MISTAKE: ["allows_mate", "missed_mate", "hangs_piece", "missed_tactic"],
    C.MISS: ["missed_mate", "missed_tactic"],
    C.BLUNDER: ["allows_mate", "missed_mate", "hangs_piece", "missed_tactic"],
}

# Lines used client-side by the Retry / Show best buttons
INTERACTIVE = {
    "retry_start": [
        "Give it another go. What would you play here?",
        "Let's rewind. Can you find a better move?",
        "Take your time and look for something stronger.",
        "Your turn. There's a better move in this position.",
    ],
    "retry_success": [
        "That's it! {best} is the move. Well done!",
        "Yes! You found {best}.",
        "Exactly! {best} was the one. Great job!",
        "Perfect. {best} is what the position was asking for.",
    ],
    "retry_fail": [
        "Not quite. Try again!",
        "That's not it. Look for something more forcing.",
        "Hmm, there's better. Have another look.",
        "Close, but no. Think about checks, captures and threats.",
    ],
    "show_best": [
        "The best move was {best}.",
        "I would have played {best}.",
        "Here it is: {best} was the strongest move.",
        "Take a look at {best}. That was the idea.",
    ],
    "intro": [
        "Let's go through the game together. Use the arrows to step through the moves.",
        "Ready when you are! Press Next and I'll tell you what I think of each move.",
    ],
}


def _voice(mover, hero):
    """Pronoun set for the side that moved."""
    if hero is None:
        name, other = ("White", "Black") if mover == "w" else ("Black", "White")
        return {"Subj": name, "subj": name, "poss": name + "'s",
                "Opp": other, "opp": other, "opp_poss": other + "'s"}
    if mover == hero:
        return {"Subj": "You", "subj": "you", "poss": "your",
                "Opp": "Your opponent", "opp": "your opponent",
                "opp_poss": "your opponent's"}
    return {"Subj": "Your opponent", "subj": "your opponent", "poss": "their",
            "Opp": "You", "opp": "you", "opp_poss": "your"}


def _pick_context(result):
    """First context (by priority) that applies and has templates."""
    cls, tags, info = result["cls"], result["tags"], result["info"]
    for context in CONTEXT_PRIORITY.get(cls, []):
        if context == "opening":
            if info.get("opening"):
                return context
        elif context in tags and (cls, context) in TEMPLATES:
            return context
    return None


def message_for(result, hero=None, seed=0, used=None, lang="en"):
    """Build ``{"title", "text", "expression"}`` for one classified move.

    ``used`` is a per-game counter so consecutive moves with the same
    classification/context cycle through the variants instead of repeating.
    """
    used = used if used is not None else {}
    cls, info = result["cls"], result["info"]
    context = _pick_context(result)
    key = (cls, context)
    bank = coach_es.TEMPLATES if lang == "es" else TEMPLATES
    variants = bank.get(key) or bank[(cls, None)]
    count = used.get(key, 0)
    used[key] = count + 1
    template = variants[(seed + count) % len(variants)]

    best_san = result["best"]["san"] if result.get("best") else result["san"]
    piece = info.get("piece", "piece")
    if context == "hangs_piece":
        piece = info.get("hung", piece)
    elif context == "promotion":
        piece = info.get("promoted", "queen")
    material = info.get("material", "material")
    if context == "missed_tactic":
        material = info.get("best_material", "material")
    n = {"mate_found": info.get("mate_n"), "missed_mate": info.get("missed_mate_n"),
         "allows_mate": info.get("allows_mate_n")}.get(context) or ""

    values = {"move": result["san"], "best": best_san, "piece": piece,
              "captured": info.get("captured", "piece"), "material": material,
              "n": n, "opening": info.get("opening", "")}
    if lang == "es":
        who = coach_es.voice(result["color"], hero)
        values.update({"pieza": coach_es.piece(piece), "capturada": coach_es.piece(values["captured"]),
                       "material": coach_es.material(material), **who})
        return {"title": coach_es.TITLES[cls].format(move=result["san"]),
                "text": coach_es.render(template, values, who["hero"]),
                "expression": EXPRESSIONS[cls]}
    values.update(_voice(result["color"], hero))
    return {
        "title": TITLES[cls].format(move=result["san"]),
        "text": template.format(**values),
        "expression": EXPRESSIONS[cls],
    }


# --------------------------------------------------------------------------
# "Explain why": the concrete reason behind a classification
# --------------------------------------------------------------------------
EXPLAINED = (C.BRILLIANT, C.GREAT, C.MISS, C.INACCURACY, C.MISTAKE, C.BLUNDER)


def _numbered(move_number, white_first, sans):
    """SAN moves with move numbers: "14...Qxd4 15.Nxd4 Rxd4"."""
    out, number, white = [], move_number, white_first
    for index, san in enumerate(sans):
        if white:
            out.append(f"{number}.{san}")
        else:
            out.append(f"{number}...{san}" if index == 0 else san)
            number += 1
        white = not white
    return " ".join(out)


# Phrases of "Explain why". "[yours|theirs]" picks a verb form by who moved
# (see coach_es.render); coach_es.EXPLAIN has the same keys in Spanish.
EXPLAIN = {"en": {
    "offers": "{move} puts the {piece} where it can be taken, on purpose.",
    "gives_up": "{move} gives up material on purpose.",
    "worth_it": "Even after the best reply, {reply}, [you keep|{subj} keeps] winning chances of "
                "{after}%: what [you get|{subj} gets] in return is worth more than the material.",
    "refutes": "{prev} was a mistake, and {move} is the move that punishes it.",
    "only_move": "It was the only move that works: the next best, {second}, would have cost "
                 "about {gap}% of the winning chances.",
    "miss_intro": "{prev} was a mistake by {opp}, and this was the moment to punish it.",
    "allows_mate": "{move} allows a forced checkmate in {n}, starting with {reply}.",
    "hangs": "{move} leaves the {piece} without enough protection: {reply} wins it.",
    "missed_mate": "There was a forced checkmate in {n}, starting with {best}.",
    "wins_material": "After {move}, the reply {reply} wins {material}.",
    "easier": "{move} is playable, but it makes things easier for {opp} after {reply}.",
    "back_in": "{move} loses no material right away, but after {reply} the advantage is gone.",
    "takes_over": "{move} loses no material right away, but after {reply} the initiative belongs to {opp}.",
    "best_tactic": "{best} was the move: it wins {material}.",
    "best_punish": "{best} was the punishment; {move} let the chance go.",
    "best_advantage": "{best} kept {poss} advantage.",
    "best_balance": "{best} kept the game balanced.",
    "best_defence": "{best} was the most stubborn defence.",
    "chances": "{Poss} winning chances went from {before}% to {after}%.",
    "label_follows": "What follows", "label_after": "After {move}", "label_better": "Better",
}, "es": coach_es.EXPLAIN}


def explain(result, prev=None, hero=None, lang="en"):
    """Why a move got its classification, in two or three short sentences.

    Uses what the engine saw: the opponent's best continuation after the move
    (``reply_line``), the best line that was available, and the winning chances
    before and after. Returns ``{"text": [sentences], "lines": [{label, moves}]}``
    or None for classifications that need no explanation (Best, Book...).
    """
    cls = result["cls"]
    if cls not in EXPLAINED:
        return None
    tags, info = result["tags"], result["info"]
    white = result["color"] == "w"
    move, number = result["san"], result["move_number"]
    best, second = result.get("best"), result.get("second")
    reply_line = result.get("reply_line") or []
    reply = reply_line[0] if reply_line else None
    before, after = round(result["win_before"]), round(result["win_after"])
    drop = result.get("material_drop", 0)

    # ---- words for the chosen language
    spanish = lang == "es"
    phrases = EXPLAIN["es" if spanish else "en"]
    piece_word = coach_es.piece if spanish else (lambda name: name)
    material_word = coach_es.material if spanish else (lambda phrase: phrase)
    if spanish:
        values = coach_es.voice(result["color"], hero)
        is_hero = values["hero"]
    else:
        values = _voice(result["color"], hero)
        values["Poss"] = values["poss"][0].upper() + values["poss"][1:]
        is_hero = values["subj"] == "you"
    values.update({"move": move, "reply": reply, "prev": prev["san"] if prev else None,
                   "best": best["san"] if best else None, "second": second["san"] if second else None,
                   "before": before, "after": after, "gap": info.get("gap"),
                   "piece": info.get("piece", "piece"), "pieza": piece_word(info.get("piece", "piece")),
                   "material": material_word(C.material_phrase(drop)), "n": ""})
    text, lines = [], []

    def say(key, **extra):
        text.append(coach_es.render(phrases[key], {**values, **extra}, is_hero))

    def line(key, moves):
        lines.append({"label": phrases[key].format(move=move), "moves": moves})

    reply_moves = _numbered(number if white else number + 1, not white, reply_line)
    best_moves = _numbered(number, white, best["pv_san"][:config.EXPLAIN_LINE_PLIES]) if best else ""

    if cls == C.BRILLIANT:
        say("gives_up" if "capture" in tags else "offers")
        if reply:
            say("worth_it")
            line("label_follows", reply_moves)
        return {"text": text, "lines": lines}

    if cls == C.GREAT:
        if "refutes" in tags and prev:
            say("refutes")
        if second and info.get("gap"):
            say("only_move")
        if reply:
            line("label_follows", reply_moves)
        return {"text": text, "lines": lines}

    # ---- inaccuracy / mistake / blunder / miss: what went wrong...
    wins_material = bool(reply) and (drop >= config.EXPLAIN_MIN_MATERIAL or (drop >= 1 and "x" in reply))
    show_reply = True
    if cls == C.MISS and prev and "missed_mate" not in tags:
        say("miss_intro")
    if "allows_mate" in tags:
        say("allows_mate", n=info["allows_mate_n"])
    elif "hangs_piece" in tags:
        say("hangs", piece=info["hung"], pieza=piece_word(info["hung"]))
    elif "missed_mate" in tags and best:
        say("missed_mate", n=info["missed_mate_n"])
        show_reply = False
    elif cls == C.MISS:
        show_reply = False                                # a miss is about the chance, not the reply
    elif wins_material:
        say("wins_material")
    elif reply and cls == C.INACCURACY:
        say("easier")
    elif reply:
        say("back_in" if after >= 45 else "takes_over")
    if reply and show_reply:
        line("label_after", reply_moves)

    # ...and what was better
    if best and not result["is_best"]:
        if "missed_mate" in tags:
            pass                                             # already said above
        elif "missed_tactic" in tags:
            say("best_tactic", material=material_word(info.get("best_material", "material")))
        elif cls == C.MISS:
            say("best_punish")
        elif before >= 65:
            say("best_advantage")
        elif before >= 40:
            say("best_balance")
        else:
            say("best_defence")
        line("label_better", best_moves)
    say("chances")
    return {"text": text, "lines": lines}


def interactive(lang="en"):
    """Lines used client-side by the Retry / Show best buttons, in the given language."""
    return coach_es.INTERACTIVE if lang == "es" else INTERACTIVE


def annotate(results, game_id="", hero=None, lang="en"):
    """Attach a ``coach`` message (and its ``explain``) to every classified move (in place)."""
    seed = int(hashlib.sha1(game_id.encode()).hexdigest(), 16) % 997
    used = {}
    prev = None
    for result in results:
        result["coach"] = message_for(result, hero=hero, seed=seed, used=used, lang=lang)
        result["coach"]["explain"] = explain(result, prev, hero, lang)
        prev = result
    return results


# --------------------------------------------------------------------------
# Game summary comment
# --------------------------------------------------------------------------
_NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]


def _count(n, noun):
    word = _NUMBERS[n] if n < len(_NUMBERS) else str(n)
    return f"{word} {noun}{'' if n == 1 else 's'}"


def summary_comment(results, counts, accuracy, result, hero=None, lang="en"):
    """One or two sentences describing the whole game.

    ``counts`` is {"w": {label: n}, "b": {...}}, ``result`` the PGN result.
    Returns ``{"text", "expression"}``.
    """
    if lang == "es":
        return coach_es.summary_comment(results, counts, accuracy, result, hero)
    errors = sum(counts[c].get(k, 0) for c in "wb" for k in (C.MISTAKE, C.BLUNDER, C.MISS))
    accs = [a for a in accuracy.values() if a is not None]
    if errors >= 5:
        opener = "A sharp game!"
    elif accs and min(accs) >= 88:
        opener = "A clean, high-quality game."
    elif len(results) < 40:
        opener = "A short one!"
    else:
        opener = "A real fight."

    winner = {"1-0": "w", "0-1": "b"}.get(result)
    if hero is None:
        names = {"w": "White", "b": "Black"}
        parts = []
        for color in "wb":
            if accuracy[color] is not None:
                parts.append(f"{names[color]} played at {accuracy[color]:.0f}% accuracy")
        text = opener + " " + " and ".join(parts) + "."
        if winner:
            loser = "b" if winner == "w" else "w"
            blunders = counts[loser].get(C.BLUNDER, 0)
            if blunders:
                text += f" {_count(blunders, 'blunder').capitalize()} by {names[loser]} decided it."
            else:
                text += f" {names[winner]} was simply more precise."
        elif result == "1/2-1/2":
            text += " In the end the point was split."
        return {"text": text, "expression": "thinking"}

    opp = "b" if hero == "w" else "w"
    mine, theirs = counts[hero], counts[opp]
    brilliant, great = mine.get(C.BRILLIANT, 0), mine.get(C.GREAT, 0)
    if brilliant:
        first = f"You found {_count(brilliant, 'brilliant move')}"
    elif great:
        first = f"You found {_count(great, 'great move')}"
    elif accuracy[hero] is not None and accuracy[hero] >= 85:
        first = "You played very accurately"
    else:
        first = "You had your chances"

    my_blunders, their_blunders = mine.get(C.BLUNDER, 0), theirs.get(C.BLUNDER, 0)
    my_misses = mine.get(C.MISS, 0)
    if winner == hero:
        if their_blunders:
            second = f"and made your opponent's {_count(their_blunders, 'blunder')} count."
        else:
            second = "and converted the advantage cleanly."
        expression = "happy"
    elif winner == opp:
        if my_blunders:
            second = f"but {_count(my_blunders, 'blunder')} decided it."
        elif my_misses:
            second = f"but {_count(my_misses, 'missed chance')} cost you."
        else:
            second = "but your opponent was just a bit sharper today."
        expression = "worried"
    else:
        second = "and in the end the point was split."
        expression = "thinking"
    return {"text": f"{opener} {first} {second}", "expression": expression}

"""Spanish coach: the same bank as coach.py (classification x context), the
"Explain why" phrases and the game summary, used when the language is "es".

Classification names follow chess.com in Spanish (Brillante, Genial, Mejor,
Excelente, Buena, Libro, Imprecisión, Error, Omisión, Error grave, Forzada).

Spanish verbs change with the subject, so a template can hold two forms:
    "[Viste|Vio] la táctica"   ->  first form when the user made the move,
                                   second for the opponent / a neutral voice.
Placeholders: {move} {best} {pieza} {capturada} (both with article: "la dama")
              {material} {n} {opening} {quien} (who moved, third person)
"""
import re

from analysis import classify as C

TITLES = {
    C.BRILLIANT: "{move} es brillante", C.GREAT: "{move} es una jugada genial",
    C.BEST: "{move} es la mejor", C.EXCELLENT: "{move} es excelente",
    C.GOOD: "{move} es buena", C.BOOK: "{move} es de libro",
    C.FORCED: "{move} es forzada", C.INACCURACY: "{move} es una imprecisión",
    C.MISTAKE: "{move} es un error", C.MISS: "{move} es una omisión",
    C.BLUNDER: "{move} es un error grave",
}

PIECES = {"pawn": "el peón", "knight": "el caballo", "bishop": "el alfil", "rook": "la torre",
          "queen": "la dama", "king": "el rey", "piece": "la pieza"}
MATERIAL = {"a pawn": "un peón", "material": "material", "a piece": "una pieza",
            "a rook": "una torre", "a queen": "una dama", "the queen": "la dama"}

TEMPLATES = {
    (C.BRILLIANT, "tactic"): [
        "[Viste|{Quien} vio] la oportunidad de ganar con una bonita táctica, ¡y la [aprovechaste|aprovechó]!",
        "¡Guau! Se entrega material y la táctica funciona a la perfección.",
        "Un golpe espectacular. El sacrificio gana {material} por la fuerza.",
        "¡Eso es calcular! {move} sacrifica, y lo que sigue lo devuelve todo.",
    ],
    (C.BRILLIANT, "checkmate"): [
        "Un sacrificio que termina en jaque mate. ¡No hay nada más bonito!",
        "¡Brillante! El material no importaba, solo el rey.",
        "El final perfecto: un sacrificio y el rey no tiene adónde ir.",
    ],
    (C.BRILLIANT, None): [
        "Un sacrificio de verdad, y es totalmente correcto. ¡Brillante!",
        "¡Guau! Se ofrece material y al motor le encanta.",
        "Hay que tener valor. {move} entrega material a cambio de una iniciativa duradera.",
        "Pocos jugadores considerarían siquiera {move}. ¡Soberbio!",
        "El material no lo es todo. {move} lo demuestra.",
    ],
    (C.GREAT, "only_move"): [
        "Era la única jugada que lo sostenía todo. ¡Gran hallazgo!",
        "Todo lo demás era claramente peor. ¡[Encontraste|{Quien} encontró] la única buena!",
        "Un momento crítico, y la jugada fue exactamente la correcta.",
        "La única jugada, y nada obvia. ¡Bien visto!",
    ],
    (C.GREAT, "refutes"): [
        "El error anterior se castigó de inmediato. ¡Jugada genial!",
        "¡Esa es la refutación! {move} muestra por qué la última jugada era mala.",
        "El castigo exacto. La jugada anterior va a pesar.",
        "¡Fino! El error estaba ahí para aprovecharse, y {move} lo hace.",
    ],
    (C.GREAT, None): [
        "Una jugada genial en un momento crítico.",
        "¡Gran hallazgo! Era mucho más fuerte que las alternativas.",
        "Precisa y fuerte. {move} era la jugada que había que encontrar.",
        "Esa era difícil de ver. ¡Muy bien!",
    ],
    (C.BEST, "checkmate"): [
        "¡Jaque mate! Un final limpio.",
        "Y eso es mate. ¡Bien jugado!",
        "¡Se acabó! {move} es jaque mate.",
        "El rey no tiene escape. ¡Jaque mate!",
    ],
    (C.BEST, "mate_found"): [
        "¡Así se hace! Ahora hay mate forzado en {n}.",
        "El camino más preciso: viene el jaque mate en {n}.",
        "La secuencia de mate está en marcha. ¡Faltan {n}!",
        "Perfecto. El rey no sobrevive a esto: mate en {n}.",
    ],
    (C.BEST, "tactic"): [
        "¡Bien visto! Eso gana {material}.",
        "Exacto. Esta táctica se lleva {material}.",
        "La mejor jugada, y gana {material}.",
        "¡Buen ojo! {move} gana {material}.",
    ],
    (C.BEST, "recapture"): [
        "La forma correcta de recapturar.",
        "Se recupera lo capturado y se mantiene el equilibrio.",
        "Una recaptura natural, y la mejor.",
        "Recapturar con {pieza} era lo más preciso.",
    ],
    (C.BEST, "castle"): [
        "La seguridad del rey primero. El enroque era la mejor jugada.",
        "El rey queda a salvo y la torre entra en juego. ¡La mejor!",
        "Enroque en el momento justo. Exactamente lo que yo habría jugado.",
        "Rey seguro, torres conectadas. Perfecto.",
    ],
    (C.BEST, "promotion"): [
        "Una pieza nueva en el tablero. ¡La mejor jugada!",
        "El peón llegó hasta el final. ¡Bien hecho!",
        "¡Coronación! Era la forma más precisa de hacerlo.",
        "El viaje de ese peón termina en gloria. La mejor jugada.",
    ],
    (C.BEST, "capture"): [
        "La mejor captura del tablero.",
        "Capturar era lo correcto. Exactamente lo que yo habría jugado.",
        "Se captura {capturada}, y era la jugada más precisa.",
        "Una buena captura. El motor está totalmente de acuerdo.",
    ],
    (C.BEST, "check"): [
        "Un jaque fuerte, y la mejor jugada de la posición.",
        "¡Jaque! Era la jugada más precisa.",
        "Sin dejar respirar al rey. ¡La mejor jugada!",
        "Ese jaque era justo lo que pedía la posición.",
    ],
    (C.BEST, "endgame"): [
        "Técnica precisa de final. Era la mejor jugada.",
        "En el final cada tiempo cuenta, y este era el correcto.",
        "Justo lo que pedía la posición. ¡Técnica limpia!",
        "La primera opción del motor. Los finales premian esta precisión.",
    ],
    (C.BEST, None): [
        "Exactamente lo que yo habría jugado.",
        "La mejor jugada de la posición. ¡Bien!",
        "Es la primera opción del motor.",
        "¡En el clavo! {move} era la jugada más fuerte.",
        "No había nada mejor. ¡La mejor jugada!",
        "Justo en el blanco.",
    ],
    (C.EXCELLENT, "capture"): [
        "Una buena captura. Casi tan buena como la mejor jugada.",
        "Capturar {capturada} fue una decisión excelente.",
        "¡Excelente! Esa captura mantiene todo bajo control.",
        "Fuerte y sencilla. El motor apenas prefiere otra cosa.",
    ],
    (C.EXCELLENT, "endgame"): [
        "Técnica excelente. El final está en buenas manos.",
        "Muy precisa. Mantiene el final bien encaminado.",
        "Nada que objetar. Una buena jugada de final.",
        "Una excelente decisión práctica en el final.",
    ],
    (C.EXCELLENT, None): [
        "Una jugada excelente. Apenas por detrás de la primera opción del motor.",
        "¡Muy fuerte! {best} era mínimamente mejor, pero esto está muy bien.",
        "Excelente. La posición sigue justo donde debía estar.",
        "Es una jugada muy precisa.",
        "Casi perfecta. Nada de qué quejarse.",
    ],
    (C.GOOD, None): [
        "Una jugada buena y sólida.",
        "Está bien. {best} era un poco más precisa.",
        "Buena jugada. Había algo ligeramente mejor: {best}.",
        "¡Razonable! Mantiene la posición sana.",
        "Una opción decente, aunque {best} le pedía un poco más a la posición.",
    ],
    (C.BOOK, "opening"): [
        "{opening}. Todavía en teoría, sólido y tranquilo.",
        "Esto es la {opening}. Un camino muy conocido.",
        "Jugada de libro. Estamos en la {opening}.",
        "{opening}. Nada nuevo aún: los dos conocen la teoría.",
        "Directo del libro: {opening}.",
    ],
    (C.BOOK, None): [
        "Una jugada normal de apertura.",
        "Seguimos en teoría de aperturas.",
        "Jugada de libro. Nada que añadir todavía.",
        "Teoría conocida. Seguimos.",
    ],
    (C.FORCED, None): [
        "La única jugada legal, así que no había elección.",
        "Forzada. No había otra cosa que jugar.",
        "Aquí no había nada que decidir: era la única jugada.",
        "Solo había una jugada legal en la posición.",
    ],
    (C.INACCURACY, "missed_tactic"): [
        "No está mal, pero {best} habría ganado {material}.",
        "Un poco imprecisa. Se podía ganar {material} con {best}.",
        "Se escapa una oportunidad: {best} se llevaba {material}.",
        "Jugable, aunque {best} era una mejora concreta.",
    ],
    (C.INACCURACY, None): [
        "Un poco imprecisa. {best} era mejor intento.",
        "No es la más precisa. {best} conservaba más ventaja.",
        "Esto regala un poquito. Mejor {best}.",
        "Una imprecisión. {best} habría sido más fuerte.",
        "Ligeramente desviada. La jugada era {best}.",
    ],
    (C.MISTAKE, "allows_mate"): [
        "¡Cuidado! Esto permite un mate forzado en {n}.",
        "Se mete en una red de mate: mate en {n}. {best} lo evitaba.",
        "Un error. El rey queda en serio peligro: mate en {n}.",
        "Esto permite forzar mate en {n}. {best} era necesaria.",
    ],
    (C.MISTAKE, "missed_mate"): [
        "¡Aquí había jaque mate en {n}! Busca {best}.",
        "Había un mate forzado en {n}, empezando con {best}.",
        "El rey estaba listo para recibir mate en {n}. La jugada era {best}.",
        "¡Se escapó! {best} llevaba al jaque mate en {n}.",
    ],
    (C.MISTAKE, "hangs_piece"): [
        "Eso deja {pieza} en problemas. {best} era más segura.",
        "Un error: {pieza} se puede capturar sin más. {best} era mejor.",
        "Después de esto {pieza} no está a salvo. {best} lo mantenía todo protegido.",
        "Esto pierde {pieza}. {best} habría sostenido la posición.",
    ],
    (C.MISTAKE, "missed_tactic"): [
        "Un error. {best} habría ganado {material}.",
        "Se pierde una oportunidad: {best} se llevaba {material}.",
        "Aquí se podía ganar {material} con {best}.",
        "La jugada fuerte, {best}, ganaba {material}. Esto lo deja pasar.",
    ],
    (C.MISTAKE, None): [
        "Eso es un error. {best} era claramente mejor.",
        "Esto entrega buena parte de la ventaja. La jugada era {best}.",
        "No es la idea correcta. {best} habría mantenido todo bajo control.",
        "Un error. Mira otra vez {best}.",
        "Esto complica las cosas. El camino era {best}.",
    ],
    (C.MISS, "missed_mate"): [
        "¡Aquí había jaque mate en {n}! Busca {best}.",
        "Una oportunidad perdida: {best} forzaba mate en {n}.",
        "La partida podía terminar aquí. ¡{best} era mate en {n}!",
        "¡Tan cerca! {best} habría iniciado un mate forzado en {n}.",
    ],
    (C.MISS, "missed_tactic"): [
        "La jugada anterior fue un error, y {best} la habría castigado ganando {material}.",
        "¡Oportunidad perdida! {best} ganaba {material}.",
        "La última jugada era un error, y {best} se llevaba {material}.",
        "Había {material} para llevarse con {best}.",
    ],
    (C.MISS, None): [
        "La jugada anterior fue un error, pero {best} la habría castigado.",
        "Una oportunidad perdida. {best} aprovechaba del todo la última jugada.",
        "La última jugada era un error, y {best} era la forma de explotarlo.",
        "Esto deja escapar al rival. {best} era mucho más fuerte.",
        "¡La oportunidad estaba ahí! {best} habría cambiado la partida.",
    ],
    (C.BLUNDER, "allows_mate"): [
        "¡Oh, no! Esto permite jaque mate en {n}.",
        "Un error grave: ahora hay mate forzado en {n}. {best} era imprescindible.",
        "Eso pierde en el acto. Es mate en {n}.",
        "El rey no sobrevive a esto: mate en {n}. {best} aguantaba.",
    ],
    (C.BLUNDER, "missed_mate"): [
        "¡Aquí había jaque mate en {n}! Busca {best}.",
        "Un error grave: {best} era mate en {n}, y ahora la victoria se ha ido.",
        "El mate en {n} estaba ahí mismo con {best}.",
        "Ay. {best} forzaba jaque mate en {n}, y esto lo tira por la borda.",
    ],
    (C.BLUNDER, "hangs_piece"): [
        "¡Ay! Eso deja {pieza} colgando. {best} era más segura.",
        "Un error grave: {pieza} está perdida sin más. {best} era mucho mejor.",
        "Eso cuelga {pieza}. {best} la habría mantenido a salvo.",
        "Queda sin defensa {pieza}. La jugada era {best}.",
    ],
    (C.BLUNDER, "missed_tactic"): [
        "Un error grave. {best} habría ganado {material}.",
        "Esto tira una gran oportunidad: {best} ganaba {material}.",
        "{best} se llevaba {material}. Después de esto, se da la vuelta la partida.",
        "Ay. Se podía ganar {material} con {best}.",
    ],
    (C.BLUNDER, None): [
        "Ay, eso es un error grave. {best} era necesaria.",
        "Esto cambia la partida. {best} era muchísimo mejor.",
        "Un error serio. {best} habría mantenido viva la posición.",
        "Eso regala la partida. La jugada correcta era {best}.",
        "Un error grave. Compáralo con {best} y la diferencia es enorme.",
    ],
}

INTERACTIVE = {
    "retry_start": [
        "Inténtalo otra vez. ¿Qué jugarías aquí?",
        "Rebobinemos. ¿Encuentras una jugada mejor?",
        "Tómate tu tiempo y busca algo más fuerte.",
        "Te toca. Hay una jugada mejor en esta posición.",
    ],
    "retry_success": [
        "¡Eso es! {best} es la jugada. ¡Bien hecho!",
        "¡Sí! Encontraste {best}.",
        "¡Exacto! Era {best}. ¡Muy bien!",
        "Perfecto. {best} es lo que pedía la posición.",
    ],
    "retry_fail": [
        "No del todo. ¡Inténtalo de nuevo!",
        "No es esa. Busca algo más forzado.",
        "Mmm, hay algo mejor. Mira otra vez.",
        "Cerca, pero no. Piensa en jaques, capturas y amenazas.",
    ],
    "show_best": [
        "La mejor jugada era {best}.",
        "Yo habría jugado {best}.",
        "Aquí está: {best} era la jugada más fuerte.",
        "Mira {best}. Esa era la idea.",
    ],
    "intro": [
        "Repasemos la partida juntos. Usa las flechas para avanzar por las jugadas.",
        "¡Cuando quieras! Pulsa Siguiente y te digo qué pienso de cada jugada.",
    ],
}

# "Explain why" phrases (same keys as coach.EXPLAIN["en"])
EXPLAIN = {
    "offers": "{move} deja {pieza} donde se puede capturar, a propósito.",
    "gives_up": "{move} entrega material a propósito.",
    "worth_it": "Incluso tras la mejor respuesta, {reply}, [conservas|{quien} conserva] un {after}% de "
                "probabilidades de ganar: lo que se obtiene a cambio vale más que el material.",
    "refutes": "{prev} fue un error, y {move} es la jugada que lo castiga.",
    "only_move": "Era la única jugada que funciona: la siguiente mejor, {second}, habría costado "
                 "cerca de {gap}% de las probabilidades de ganar.",
    "miss_intro": "{prev} fue un error, y este era el momento de castigarlo.",
    "allows_mate": "{move} permite un mate forzado en {n}, que empieza con {reply}.",
    "hangs": "{move} deja {pieza} sin suficiente defensa, y cae con {reply}.",
    "missed_mate": "Había mate forzado en {n}, empezando con {best}.",
    "wins_material": "Tras {move}, la respuesta {reply} gana {material}.",
    "easier": "{move} es jugable, pero tras {reply} la posición es más cómoda para {otro}.",
    "back_in": "{move} no pierde material de inmediato, pero tras {reply} la ventaja desaparece.",
    "takes_over": "{move} no pierde material de inmediato, pero tras {reply} la iniciativa pasa a {otro}.",
    "best_tactic": "{best} era la jugada: gana {material}.",
    "best_punish": "{best} era el castigo; {move} deja pasar la oportunidad.",
    "best_advantage": "{best} mantenía la ventaja.",
    "best_balance": "{best} mantenía la partida igualada.",
    "best_defence": "{best} era la defensa más tenaz.",
    "chances": "[Tus|Sus] probabilidades de ganar pasaron de {before}% a {after}%.",
    "label_follows": "Lo que sigue", "label_after": "Tras {move}", "label_better": "Mejor",
}


def voice(mover, hero):
    """Who moved ({quien}/{Quien}) and the other side ({otro}), plus whether it was the user."""
    if hero is None:
        name, other = ("el blanco", "el negro") if mover == "w" else ("el negro", "el blanco")
        return {"quien": name, "Quien": name.capitalize(), "otro": other, "hero": False}
    if mover == hero:
        return {"quien": "tú", "Quien": "Tú", "otro": "tu rival", "hero": True}
    return {"quien": "tu rival", "Quien": "Tu rival", "otro": "ti", "hero": False}


def render(template, values, is_hero):
    """Pick the "[yours|theirs]" form of every bracket, then fill the placeholders."""
    text = re.sub(r"\[([^|\]]*)\|([^\]]*)\]", lambda m: m.group(1 if is_hero else 2), template)
    return text.format(**values)


def piece(name):
    return PIECES.get(name, "la pieza")


def material(phrase):
    return MATERIAL.get(phrase, "material")


# --------------------------------------------------------------------------
# Game summary
# --------------------------------------------------------------------------
_NUMBERS = ["ningún", "un", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve"]
_PLURALS = {"error grave": "errores graves", "jugada brillante": "jugadas brillantes",
            "jugada genial": "jugadas geniales", "oportunidad perdida": "oportunidades perdidas"}


def _count(n, noun):
    """"un error grave" / "dos jugadas geniales" (feminine nouns take "una")."""
    word = _NUMBERS[n] if n < len(_NUMBERS) else str(n)
    if n == 1 and noun.startswith(("jugada", "oportunidad")):
        word = "una"
    return f"{word} {noun if n == 1 else _PLURALS[noun]}"


def summary_comment(results, counts, accuracy, result, hero=None):
    """Spanish version of coach.summary_comment (same rules, same return shape)."""
    errors = sum(counts[c].get(k, 0) for c in "wb" for k in (C.MISTAKE, C.BLUNDER, C.MISS))
    accs = [a for a in accuracy.values() if a is not None]
    if errors >= 5:
        opener = "¡Una partida movida!"
    elif accs and min(accs) >= 88:
        opener = "Una partida limpia y de gran calidad."
    elif len(results) < 40:
        opener = "¡Una partida corta!"
    else:
        opener = "Una verdadera lucha."

    winner = {"1-0": "w", "0-1": "b"}.get(result)
    if hero is None:
        names = {"w": "el blanco", "b": "el negro"}
        parts = [f"{names[c]} jugó con un {accuracy[c]:.0f}% de precisión"
                 for c in "wb" if accuracy[c] is not None]
        text = opener + " " + " y ".join(parts).capitalize() + "."
        if winner:
            loser = "b" if winner == "w" else "w"
            blunders = counts[loser].get(C.BLUNDER, 0)
            if blunders:
                verb = "Lo decidió" if blunders == 1 else "Lo decidieron"
                text += f" {verb} {_count(blunders, 'error grave')} del {names[loser][3:]}."
            else:
                text += f" {names[winner].capitalize()} fue simplemente más preciso."
        elif result == "1/2-1/2":
            text += " Al final se repartió el punto."
        return {"text": text, "expression": "thinking"}

    opp = "b" if hero == "w" else "w"
    mine, theirs = counts[hero], counts[opp]
    brilliant, great = mine.get(C.BRILLIANT, 0), mine.get(C.GREAT, 0)
    if brilliant:
        first = f"Encontraste {_count(brilliant, 'jugada brillante')}"
    elif great:
        first = f"Encontraste {_count(great, 'jugada genial')}"
    elif accuracy[hero] is not None and accuracy[hero] >= 85:
        first = "Jugaste con mucha precisión"
    else:
        first = "Tuviste tus oportunidades"

    my_blunders, their_blunders = mine.get(C.BLUNDER, 0), theirs.get(C.BLUNDER, 0)
    my_misses = mine.get(C.MISS, 0)
    if winner == hero:
        if their_blunders:
            second = f"y aprovechaste {_count(their_blunders, 'error grave')} de tu rival."
        else:
            second = "y convertiste la ventaja sin problemas."
        expression = "happy"
    elif winner == opp:
        if my_blunders:
            second = f"pero {_count(my_blunders, 'error grave')} lo {'decidió' if my_blunders == 1 else 'decidieron'}."
        elif my_misses:
            second = f"pero {_count(my_misses, 'oportunidad perdida')} te {'costó' if my_misses == 1 else 'costaron'} la partida."
        else:
            second = "pero tu rival estuvo un poco más fino hoy."
        expression = "worried"
    else:
        second = "y al final se repartió el punto."
        expression = "thinking"
    return {"text": f"{opener} {first} {second}", "expression": expression}

# Proyecto: "Chess Review" — mi propio Game Review estilo chess.com

Quiero una app web local para analizar mis partidas de chess.com con una experiencia
parecida a su "Game Review": coach con mensajes, gráfica de evaluación, jugadas
clasificadas (Brilliant, Great, Best, Mistake, Blunder, etc.) y resumen de precisión.
Es para uso personal. Trabaja por fases. Al terminar cada fase, corre la app y los tests
y verifica que todo funcione antes de pasar a la siguiente.

## Stack
- Backend: Python 3.11+, Flask, python-chess, Stockfish (binario local; detecta la ruta
  o léela de la variable STOCKFISH_PATH en un .env). SQLite para caché de análisis.
- Frontend: HTML + JS vanilla (sin framework). Usa chess.js para la lógica, chessground
  para el tablero (con flechas y resaltado de casillas) y Chart.js para la gráfica.
- Estructura sugerida:
  app.py, analysis/ (engine.py, classify.py, coach.py, openings.py),
  templates/, static/js/, static/css/, static/img/, tests/, requirements.txt, README.md

## Fase 1 — Traer partidas
- Endpoint GET /api/games/<username>?month=YYYY-MM que use la API pública de chess.com:
  - https://api.chess.com/pub/player/{user}/games/archives → lista de meses
  - Cada archivo mensual trae las partidas con su PGN.
  - Manda un header User-Agent descriptivo (ej. "chess-review-personal/1.0").
  - Maneja errores 404 y 429 con mensajes claros.
- Pantalla inicial: input de usuario → lista de partidas recientes (rival, rating,
  resultado, control de tiempo, fecha, apertura) → botón "Review".
- También una opción para pegar un PGN manualmente.

## Fase 2 — Motor de análisis
- Para cada posición de la partida: Stockfish con MultiPV=2 y una profundidad configurable
  (default 18; opción "rápido" en 12). Guarda por ply: eval en cp o mate, la mejor jugada,
  la segunda mejor con su eval y la línea principal (PV) de unas 6 jugadas.
- Normaliza todo desde el punto de vista del jugador que mueve.
- Convierte la eval a win%: win% = 50 + 50 * (2 / (1 + exp(-0.00368208 * cp)) - 1).
  Si hay mate, usa ±10000 cp (acotado).
- Progreso en tiempo real con Server-Sent Events (GET /api/analyze/stream?game_id=...).
  En el frontend: barra de progreso con la animación "Analyzing move 23/61...".
- Guarda en caché en SQLite (llave: hash del PGN + profundidad) para no reanalizar.

## Fase 3 — Clasificación de jugadas (analysis/classify.py)
Sea `loss` = win% de la mejor jugada − win% de la jugada que se jugó (desde la
perspectiva de quien mueve). Aplica las reglas en este orden:
1. **Book**: la posición sigue dentro de teoría. Usa los TSV de aperturas de
   lichess-org/chess-openings (descárgalos al proyecto) y muestra el nombre de la apertura.
2. **Forced**: solo había una jugada legal.
3. **Brilliant**: es la mejor jugada (o loss ≤ 2) Y es un sacrificio real (la pieza queda
   colgada según Static Exchange Evaluation, o el material baja ≥ 2 puntos en las
   siguientes 2–4 jugadas de la PV) Y antes de la jugada el win% no era ya > 95
   Y después el win% es ≥ 50. No marques como brilliant los sacrificios de peón triviales.
4. **Great**: es la mejor jugada Y la segunda mejor es ≥ 15 win% peor (era la única
   buena), o refuta un error del rival.
5. **Miss**: el rival acaba de cometer un mistake o blunder, había una jugada que ganaba
   ≥ 15 win% y no la jugaste (loss ≥ 10).
6. **Best**: coincide con la jugada #1 del motor.
7. Según loss: **Excellent** < 2, **Good** < 5, **Inaccuracy** < 10, **Mistake** < 20,
   **Blunder** ≥ 20.
Precisión por jugada = clamp(103.1668 * exp(-0.04354 * loss) - 3.1669, 0, 100).
La precisión de la partida es el promedio por jugador (pondera más las posiciones
críticas, como hace Lichess, si es fácil).
Además, detecta etiquetas de contexto para el coach: captura, jaque, mate encontrado,
mate fallado, pieza colgada, táctica (ganancia de material en la PV), final, enroque,
promoción.
**Escribe tests en pytest** con posiciones conocidas (FEN) para cada clasificación:
un brilliant clásico de sacrificio, un blunder que cuelga la dama, un mate fallado, etc.

## Fase 4 — Pantalla de Review (lo más importante)
Layout de dos columnas, tema oscuro estilo app de ajedrez moderna:

**Izquierda: tablero**
- Barra de evaluación vertical animada al lado del tablero.
- En cada jugada, resalta las casillas de origen y destino con el color de su
  clasificación y pon un ícono pequeño en la esquina de la casilla destino
  (como badge circular).
- Si la jugada no fue Best, dibuja una flecha verde con la mejor jugada.
- Botones: ⏮ ◀ ▶ ⏭, voltear tablero y navegación con las flechas del teclado.

**Derecha: panel del coach**
- Un personaje coach ORIGINAL dibujado en SVG (por ejemplo un búho o un robot
  amigable con 3–4 expresiones: feliz, sorprendido, pensativo, preocupado).
  No copies el avatar ni los íconos de chess.com; diseña los tuyos.
- Globo de diálogo con un mensaje que cambia en cada jugada, con animación de
  aparición. Encabezado: ícono + "Nf5 is brilliant" / "Qxd4 is a blunder", y la eval.
- Botones: "Show best move", "Retry" (para intentar encontrar la mejor jugada en el
  tablero; si aciertas, el coach te felicita) y "Next".
- Lista de jugadas en dos columnas con el ícono de su clasificación, clickeable.

**Mensajes del coach (analysis/coach.py)**
- Banco de plantillas en inglés por clasificación × contexto, con 4–6 variantes cada una
  para que no se repitan. Usa variables como {move}, {best}, {piece}, {material}.
  Ejemplos del tono:
  - Brilliant + táctica: "You saw your chance for the win with a nice tactic and you took it!"
  - Great: "That was the only move that held everything together. Great find!"
  - Best: "Exactly what I would have played."
  - Miss: "Your opponent slipped, but {best} would have punished it."
  - Blunder + pieza colgada: "Ouch — that leaves your {piece} hanging. {best} was safer."
  - Mate fallado: "There was a checkmate in {n} here! Look for {best}."
  - Book: "{opening}. Still in theory — nice and solid."
- La expresión del coach cambia según la clasificación.

**Gráfica de evaluación (Chart.js)**
- Gráfica de área de win% (o eval acotada a ±10): blanco arriba y negro abajo,
  con la línea en 50%.
- Puntos de color sobre la línea en las jugadas notables (Brilliant, Great, Miss,
  Mistake, Blunder), con un tooltip que muestre la jugada y su clasificación.
- Clic en un punto o en cualquier parte de la gráfica → salta a esa jugada.
  Una línea vertical marca la jugada actual.

**Colores sugeridos por clasificación**
Brilliant turquesa, Great azul, Best verde, Excellent verde claro, Good verde grisáceo,
Book café claro, Inaccuracy amarillo, Mistake naranja, Miss rosa/rojo claro,
Blunder rojo, Forced gris. Íconos propios en SVG (!!, !, ★, 👍, ?!, ?, ??, libro, etc.).

## Fase 5 — Resumen de la partida
Antes de entrar a la review, muestra una pantalla de resumen:
- El coach con un comentario general ("A sharp game! You found two great moves but
  one blunder decided it.").
- Precisión de cada jugador en grande, con avatar e info de cada uno.
- Tabla con el conteo de cada clasificación por jugador (columna blancas | columna negras).
- Gráfica de evaluación en miniatura.
- Desglose por fases: apertura / medio juego / final, con un ícono de calidad en cada una.
- Botón "Start Review".

## Fase 6 (opcional) — Extras
- Página de estadísticas de mis últimas N partidas: precisión promedio, blunders por
  partida, aperturas donde más pierdo y errores bajo presión de tiempo (usa los
  %clk del PGN).
- Modo "Puzzles de mis errores": convierte cada Blunder y Miss en un puzzle.

## Reglas de trabajo
- README con la instalación (incluye cómo instalar Stockfish en Windows/Mac/Linux)
  y cómo correr la app.
- Código limpio y comentado. Pon los umbrales de clasificación en un config.py
  para poder ajustarlos.
- Al terminar cada fase, dime qué hiciste y cómo probarlo.
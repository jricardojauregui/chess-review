# Chess Review

App web local para revisar tus partidas de chess.com con una experiencia tipo
"Game Review": coach con mensajes, barra y gráfica de evaluación, jugadas
clasificadas (Brilliant, Great, Best, Mistake, Blunder…), precisión por jugador,
estadísticas y puzzles hechos con tus propios errores. Uso personal.

## Instalación

Requisitos: **Python 3.11+** y **Stockfish**.

### 1. Stockfish

| Sistema | Cómo instalarlo |
|---|---|
| **macOS** | `brew install stockfish` |
| **Linux** (Debian/Ubuntu) | `sudo apt install stockfish` (Fedora: `sudo dnf install stockfish`, Arch: `sudo pacman -S stockfish`) |
| **Windows** | `winget install Stockfish.Stockfish`, o descarga el zip de <https://stockfishchess.org/download/> y descomprímelo (por ejemplo en `C:\stockfish\`) |

La app busca el binario en este orden: variable `STOCKFISH_PATH` → el `PATH` del
sistema → rutas típicas (`/opt/homebrew/bin`, `/usr/local/bin`, `/usr/games`,
`C:\stockfish\`…). Si no lo encuentra (típico en Windows), copia `.env.example`
a `.env` y pon la ruta completa:

```
STOCKFISH_PATH=C:\stockfish\stockfish-windows-x86-64-avx2.exe
```

### 2. Dependencias de Python

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Las librerías de frontend (chessground, chess.js, Chart.js) y los TSV de
aperturas de Lichess ya vienen dentro del proyecto (`static/vendor/`,
`data/openings/`), así que no hace falta npm ni conexión para usarlas.

## Cómo correr la app

```bash
python app.py
```

Abre <http://127.0.0.1:5050>. (El puerto se cambia con `PORT=8000 python app.py`
o en `.env`; no se usa el 5000 porque en macOS lo ocupa AirPlay.)

## Cómo se usa

1. **Cuenta**: la primera vez (o si no hay cuenta vinculada) la app pregunta qué
   cuenta de chess.com quieres analizar. Se cambia o se desvincula en
   **Settings → chess.com account**. Desvincular no borra los análisis guardados.
2. **Games**: lista de tus partidas por mes. Al pasar el cursor sobre el
   **nombre del rival** sale un mini tablero con la posición final (igual en la
   tabla de Stats). También puedes abrir una partida concreta pegando su
   **ID o enlace de chess.com**.
3. **Tablero**: al abrir una partida ves el tablero de inmediato y puedes
   recorrerla. Elige un **nivel de análisis** y pulsa **Analyze game**; el
   progreso aparece en el panel del coach. El resultado se guarda en
   `data/cache.db`: cada partida solo se analiza una vez por nivel.
4. **Resumen**: comentario del coach, precisión de cada jugador (y la de
   chess.com cuando existe, como referencia), conteo de clasificaciones, gráfica
   y calidad por fase → **Start Review**. El tablero nunca sale de la pantalla:
   solo se desplaza el panel derecho.
5. **Review**: `←` `→` para moverte, `↑` `↓` inicio/fin, `F` voltea el tablero,
   `Espacio` (o el botón ▶ / ⏸) reproduce la partida sola y la pausa. Junto a
   cada jugador se ven las piezas que ha capturado y su ventaja de material.
   *Show best move* enseña la jugada del motor y su línea; *Retry* te deja buscarla.
   Las flechas y casillas siguen el esquema de colores del Game Review de
   chess.com: **naranja** = la idea principal de la jugada (lo que ataca, un
   jaque), **verde** = la jugada mejor que había, **rojo** = amenaza o problema
   (la respuesta que castiga un error), **azul** = la respuesta del rival (una
   captura). Las del caballo se dibujan en L. Los botones para moverse por la
   partida están fijos en el panel derecho, así el tablero ocupa toda la altura.
6. **¿Y si…?**: en cualquier momento mueve tú las piezas. Si juegas algo distinto
   a la partida, el motor evalúa tu jugada en vivo, la clasifica, mueve la barra
   y muestra sus **3 mejores líneas** (clic en una para jugarla). *Undo move*
   retrocede y *Back to game* (o `Esc`) vuelve a la partida.
   En las jugadas Brilliant, Great, Miss, Inaccuracy, Mistake y Blunder aparece
   **Explain why** (tecla `W`): el coach explica en dos o tres frases el motivo
   concreto (qué respuesta castiga la jugada, qué material se pierde, qué mate
   había, cuánto bajan tus probabilidades de ganar) y muestra las dos líneas.
7. **Openings**: 36 lecciones escritas a mano, más todas las aperturas con nombre
   de la base de datos. Cada lección va por pasos: primero la **lección guiada**
   de la línea principal (el coach marca tu jugada con la pieza en azul y una
   flecha, tú la juegas en el tablero y él explica para qué sirve; las respuestas
   del rival se juegan solas), después **Practice from memory** (sin flechas;
   *Hint* marca primero la pieza en azul y, si lo pides otra vez, la flecha) y,
   al terminar la línea principal, se desbloquean las **líneas extra**.
8. **Puzzles**: entrenamiento con un banco de ~9,300 puzzles de varias jugadas
   (`data/puzzles.tsv`). No salen de tus partidas: tus partidas revisadas solo
   deciden la mezcla (si fallas mates, más mates; si cuelgas piezas, más piezas
   sueltas) y la tarjeta *What I'm training you on* lo explica. Tú juegas cada
   jugada de la línea y el rival responde solo. *Hint* marca la pieza en azul y
   luego la flecha; *Show solution* reproduce la línea. Tu **puzzle rating**
   sube o baja con cada resultado y decide la dificultad de los siguientes. La
   pestaña *From my games* conserva los puzzles de tus propios Blunders y Misses.
9. **Stats**: usa la cuenta vinculada. Eliges el nivel
   y el effort y analizas en lote las partidas que falten a ese nivel.
   El lote corre en el servidor:
   puedes cambiar de página y una tarjeta abajo a la derecha muestra el progreso
   en toda la app. Mientras corre no se puede lanzar otro. **Stop** lo detiene
   y pregunta si conservar o revertir las partidas que ya había terminado.
10. **Idioma**: el botón `EN` / `ES` junto al de tema claro/oscuro cambia toda la
   app entre inglés y español. La interfaz se traduce con el diccionario de
   `static/js/i18n-es.js` y los mensajes del coach vienen del banco en español
   (`analysis/coach_es.py`, con los nombres de clasificación de chess.com:
   Brillante, Genial, Mejor, Excelente, Buena, Libro, Imprecisión, Error,
   Omisión, Error grave). Las 36 lecciones de aperturas están traducidas en
   `analysis/lessons_es.py`; los nombres de la base de aperturas y la notación
   de las jugadas (Nf3, Bc4) siguen en inglés. Al lado hay un botón para
   activar o silenciar el sonido de las jugadas.
11. **Settings** (página propia): cuenta, nivel de análisis y **effort** por
   defecto, tablero y piezas (20 tableros lisos, de madera y de piedra; 20 juegos
   de piezas, con vista previa siempre visible), tema claro/oscuro y sonido.

### Piezas Neo y Neo Wood

Son los juegos de piezas de chess.com. No vienen en el repositorio (son de
chess.com; están en `.gitignore`): se descargan para uso personal con

```bash
python scripts/fetch_pieces.py
```

Si la carpeta de un juego no existe, simplemente no aparece en Settings.

## Niveles de análisis y uso del equipo

| Nivel | Profundidad | Tope por jugada | Partida de ~35 jugadas* |
|---|---|---|---|
| Lite | 10 | 0.5 s | unos segundos |
| Fast | 12 | 1 s | unos segundos |
| **Standard** (por defecto) | 16 | 3 s | ~40 s |
| Deep | 20 | 8 s | ~2 min |
| Max | 24 | 20 s | ~10 min |

\* Medido en un Apple M5 con un solo motor (effort Low). Se definen en
`ENGINE_PRESETS` (`config.py`).

### Effort: qué tan rápido va

El **nivel** decide la calidad (profundidad); el **effort** decide cuánta CPU
se usa y por tanto la velocidad. Las posiciones de la partida se reparten entre
varios procesos de Stockfish de un hilo cada uno, así que el resultado es del
mismo tipo y llega antes (medido: 80 posiciones a profundidad 16 en 30 s con un
motor, 15.6 s con dos y 8.9 s con cuatro).

| Effort | Motores en paralelo |
|---|---|
| Low | 1 |
| **Medium** (por defecto) | la mitad de los núcleos rápidos |
| High | tres cuartos de los núcleos rápidos |
| Max | todos los núcleos rápidos |

Se elige en **Settings** o justo antes de analizar una partida. "Núcleos
rápidos" son los de rendimiento en Apple Silicon (los de eficiencia nunca se
usan y quedan para el resto del sistema). `ENGINE_MAX_WORKERS=4` en `.env` pone
un tope fijo si lo quieres.

El análisis está pensado para no castigar el equipo:

- Stockfish nunca usa más que los núcleos rápidos (un motor por núcleo, según
  el effort), con **prioridad baja** (`nice`), memoria fija y pequeña por motor,
  y cada jugada tiene un tope de tiempo: hasta Max + Max tiene un coste acotado.
- El motor **solo existe mientras se analiza**: al terminar una partida el
  proceso se cierra. El motor del modo "¿y si…?" se cierra solo tras 90 s sin uso.
- Nada corre en segundo plano y nada se analiza dos veces al mismo nivel.
- Más effort o más profundidad solo significan más calor y batería mientras
  dura el análisis; no hay riesgo para el hardware.

## Tests

```bash
python -m pytest
```

Incluyen posiciones conocidas (FEN) por clasificación: el sacrificio de dama del
mate de Legal (Brilliant), una dama colgada (Blunder), un mate en 1 fallado, una
única jugada que salva la partida (Great), un Miss tras un error del rival, etc.
Los tests que usan el motor se saltan solos si Stockfish no está instalado.

## Ajustes

Todos los umbrales están en [`config.py`](config.py): escalera de pérdida de
win% (Excellent/Good/Inaccuracy/Mistake/Blunder), condiciones de Brilliant,
Great y Miss, fórmula de precisión, fases de la partida, profundidades e hilos
del motor. La clasificación se recalcula al abrir cada review, así que un cambio
en `config.py` se aplica (tras reiniciar la app) **sin reanalizar** nada.

Notas sobre decisiones que quizá quieras tocar:

- **Great** sigue la definición publicada por chess.com (jugada "crítica para el
  resultado"): es la mejor, la segunda es ≥ `GREAT_MIN_GAP` win% peor, la mejor
  no sigue perdida (`GREAT_MIN_WIN_BEST`) y la alternativa no sigue ganada
  (`GREAT_MAX_WIN_SECOND`). Nunca lo son las recapturas, el mate en 1 ni retirar
  una pieza atacada (`GREAT_SKIP_OBVIOUS`).
- `MISSED_MATE_MAX_N = 5`: fallar un mate forzado en ≤ 5 cuenta como Miss aunque
  la posición siga ganada. `0` lo desactiva.
- `START_EVAL_ZERO`: la posición inicial siempre marca 0.00 (como chess.com) en
  vez de la pequeña ventaja que da el motor a las blancas.
- `ACCURACY_MODE = "weighted"`: la fórmula de chess.com no es pública. Comparando
  con la precisión que chess.com reporta en partidas reales, el modo ponderado
  se desvió ~5 puntos de media y el promedio simple (`"mean"`) ~18.
- `ENGINE_THREADS = 1`: a profundidad fija con MultiPV, varios hilos resultaron
  2-3× más lentos en las pruebas. Por eso la velocidad se gana con varios
  motores de un hilo (`EFFORT_LEVELS`), no con más hilos por motor.
- `ENGINE_NICE = 10`: prioridad baja del proceso del motor (0 la desactiva).
- `EXPLORE_DEPTH = 16`: profundidad del análisis en vivo al mover tú las piezas.

## Estructura

```
app.py                 Rutas Flask (páginas + API + SSE)
config.py              Umbrales y ajustes
analysis/
  engine.py            Stockfish (MultiPV=2), eval → win%
  classify.py          Clasificación, SEE/sacrificios, etiquetas, precisión
  coach.py             Banco de mensajes del coach (clasificación × contexto)
  coach_es.py          El mismo banco en español
  openings.py          Libro de aperturas (TSV de lichess-org/chess-openings)
  chesscom.py          Cliente de la API pública de chess.com
  review.py            PGN + análisis → JSON de la review y el resumen
  jobs.py              Análisis en segundo plano con progreso (SSE)
  explore.py           Análisis en vivo de una posición (modo "¿y si…?")
  stats.py             Estadísticas y puzzles de tus propios errores
  puzzles.py           Banco de puzzles de entrenamiento y perfil de debilidades
  lessons.py           Lecciones de aperturas (lessons_data.py + lessons_extra.py,
                       y su texto en español en lessons_es.py)
  store.py             SQLite: partidas, caché de análisis, perfiles, ajustes
templates/, static/    HTML, JS vanilla, CSS, librerías en static/vendor
tests/                 pytest
data/openings/         TSV de aperturas · data/cache.db se crea solo
data/puzzles.tsv       Banco de puzzles (lo regenera scripts/build_puzzles.py)
```

## API

| Endpoint | Descripción |
|---|---|
| `GET /api/games/<username>?month=YYYY-MM` | Partidas del mes (por defecto, el último) |
| `GET /api/batch` · `POST /api/batch` `{game_ids, depth}` | Estado del análisis en lote / lo inicia (409 si ya hay uno) |
| `POST /api/batch/stop` `{revert}` | Lo detiene; `revert` borra lo que ese lote había terminado |
| `POST /api/games/import` `{pgn}` | Guarda un PGN → `game_id` (sin pantalla; lo usan los tests) |
| `POST /api/games/lookup` `{ref}` | Importa una partida por ID o enlace de chess.com |
| `POST /api/explore` `{fen}` | Mejores líneas del motor para una posición |
| `GET/POST /api/settings` · `POST/DELETE /api/account` | Preferencias y cuenta vinculada |
| `GET /api/analyze/stream?game_id=&depth=` | SSE con el progreso del análisis |
| `GET /api/review/<game_id>?depth=` | Review clasificada (202 + la partida sin analizar si falta) |
| `GET /api/stats/<username>?n=` · `GET /api/puzzles/<username>?n=` | Extras |
| `POST /api/puzzles/train` `{rating, n, seen}` | Sesión de puzzles del banco, mezclada según tus errores |
| `GET /api/openings` · `GET /api/openings/lesson/<id>` · `GET /api/openings/search?q=` | Lecciones de aperturas |

## Créditos

- Tablero: [chessground](https://github.com/lichess-org/chessground) · lógica: [chess.js](https://github.com/jhlywa/chess.js) · gráficas: [Chart.js](https://www.chartjs.org/)
- Aperturas: [lichess-org/chess-openings](https://github.com/lichess-org/chess-openings)
- Puzzles: selección de la [base de puzzles de Lichess](https://database.lichess.org/#puzzles)
  (dominio público, CC0). `python scripts/build_puzzles.py` la vuelve a generar
  (descarga el inicio de la base; necesita el comando `zstd`).
- Los juegos de piezas incluidos y los sonidos de movimiento: del proyecto
  open source [Lichess (lila)](https://github.com/lichess-org/lila). Lo único
  de chess.com son las piezas Neo y Neo Wood, opcionales y fuera del repositorio
  (ver arriba). Las texturas de madera y
  piedra de los tableros se generan con filtros SVG (no son imágenes).

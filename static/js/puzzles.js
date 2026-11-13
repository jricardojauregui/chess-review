// Puzzles. Two sources, one player:
//   - Training: multi-move puzzles from the bank, mixed by the server according
//     to what you get wrong in your own games. You play every move of the
//     line; the opponent's replies are played for you. Your puzzle rating
//     moves with your results and decides how hard the next ones are.
//   - From my games: every Blunder / Miss you played, as a one-move puzzle.
// Hints come in two steps: first the piece to move (blue square), then the move (arrow).
import { Chessground } from '../vendor/chessground.min.js';
import { Chess } from '../vendor/chess.js';
import {
  $, CLS, accountName, api, badgeSVG, drawArrows, escapeHtml, legalDests, playMoveSound, showCoach,
  squareXY, store, tryMove,
} from './common.js';

const username = accountName();
const REPLY_DELAY_MS = 550;       // pause before the opponent answers
const SEEN_LIMIT = 1500;          // puzzle ids remembered so they do not repeat

const THEME_NAMES = {
  mateIn1: 'Mate in 1', mateIn2: 'Mate in 2', mateIn3: 'Mate in 3', mateIn4: 'Mate in 4', mateIn5: 'Mate in 5',
  backRankMate: 'Back-rank mate', smotheredMate: 'Smothered mate', fork: 'Fork', pin: 'Pin', skewer: 'Skewer',
  discoveredAttack: 'Discovered attack', discoveredCheck: 'Discovered check', doubleCheck: 'Double check',
  hangingPiece: 'Hanging piece', trappedPiece: 'Trapped piece', deflection: 'Deflection', attraction: 'Attraction',
  sacrifice: 'Sacrifice', defensiveMove: 'Defensive move', quietMove: 'Quiet move', promotion: 'Promotion',
  advancedPawn: 'Advanced pawn', capturingDefender: 'Removing the defender', intermezzo: 'In-between move',
  xRayAttack: 'X-ray', zugzwang: 'Zugzwang', clearance: 'Clearance', interference: 'Interference',
  exposedKing: 'Exposed king', kingsideAttack: 'Kingside attack', queensideAttack: 'Queenside attack',
  attackingF2F7: 'Attack on f2/f7', opening: 'Opening', middlegame: 'Middlegame', endgame: 'Endgame',
  rookEndgame: 'Rook endgame', pawnEndgame: 'Pawn endgame', bishopEndgame: 'Bishop endgame',
  knightEndgame: 'Knight endgame', queenEndgame: 'Queen endgame',
};
const PIECE_NAMES = { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' };

let source = store.get('puzzleSource', 'train') === 'games' ? 'games' : 'train';
let cg = null;
let queue = [];             // puzzles of the current source
let index = 0;
let P = null;               // current puzzle
let game = null;            // chess.js at the current position of the line
let step = 0;               // index in P.moves of the move to find / play next
let hintLevel = 0;          // 0 none, 1 piece highlighted, 2 arrow shown
let state = 'idle';         // idle | lead | solving | reply | done
let outcome = null;         // null | 'solved' | 'helped' | 'failed' (set once per puzzle)
let token = 0;              // cancels timers of the previous puzzle
let session = [];           // outcomes of this visit, for the progress strip
let train = null;           // last /api/puzzles/train answer (profile, k, range)
let loadingMore = false;

// ------------------------------------------------------------ saved progress
const readJSON = (key, fallback) => { try { return JSON.parse(store.get(key, '')) ?? fallback; } catch (e) { return fallback; } };
let rating = Number(store.get('puzzleRating', '')) || null;
let totals = readJSON('puzzleStats', { solved: 0, failed: 0, streak: 0, best: 0 });
let seen = readJSON('puzzleSeen', []);

/** Keep the queue and the progress in the current puzzle for this tab. */
function saveState() {
  try {
    sessionStorage.setItem('puzzleState', JSON.stringify({
      source, queue: queue.slice(index), step: state === 'done' ? P.moves.length : step, outcome, session,
    }));
  } catch (e) { /* private mode: the puzzle just restarts on reload */ }
}
function savedState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem('puzzleState'));
    return saved && saved.source === source && saved.queue && saved.queue.length ? saved : null;
  } catch (e) { return null; }
}

function remember(id) {
  seen.push(id);
  if (seen.length > SEEN_LIMIT) seen = seen.slice(-SEEN_LIMIT);
  store.set('puzzleSeen', JSON.stringify(seen));
}

// ================================================================ rendering
function setCoach(expression, cls, title, text, line = '') {
  showCoach($('#coach-avatar'), expression);
  $('#bubble-icon').innerHTML = cls ? badgeSVG(cls, 24) : '';
  $('#bubble-title').textContent = title;
  $('#bubble-text').textContent = text;
  $('#bubble-line').innerHTML = line;
  const bubble = $('#bubble');
  bubble.classList.remove('pop'); void bubble.offsetWidth; bubble.classList.add('pop');
}

const orientation = () => (P.color === 'w' ? 'white' : 'black');
const squares = uci => [uci.slice(0, 2), uci.slice(2, 4)];

/** Draw the current position. `last` = [from, to] of the last move, coloured by `cls`. */
function setBoard({ last = null, cls = 'plain', interactive = false, hint = 0 } = {}) {
  const fen = game.fen();
  const custom = new Map();
  if (last) for (const sq of last) custom.set(sq, `hl-${cls}`);
  const arrows = [];
  if (hint >= 1 && P.moves[step]) {
    const [from, to] = squares(P.moves[step]);
    custom.set(from, 'mark-hint');
    if (hint >= 2) arrows.push({ orig: from, dest: to, kind: 'hint' });
  }
  const turn = fen.split(' ')[1] === 'w' ? 'white' : 'black';
  cg.set({
    fen, orientation: orientation(), turnColor: turn, lastMove: last || undefined, check: game.inCheck(),
    highlight: { lastMove: false, check: true, custom },
    movable: { color: interactive ? turn : undefined, dests: interactive ? legalDests(game) : new Map() },
    drawable: { autoShapes: [] },
  });
  drawArrows($('#arrows'), arrows, orientation());
  const badge = $('#move-badge');
  if (last && (cls === 'best' || cls === 'mistake')) {
    const { x, y } = squareXY(last[1], orientation());
    badge.style.left = `${(x + 1) * 12.5}%`;
    badge.style.top = `${y * 12.5}%`;
    badge.innerHTML = badgeSVG(cls, 32);
    badge.hidden = false;
  } else badge.hidden = true;
}

/** How many moves the solver has to find, and how many are done. */
const solverMoves = () => Math.ceil(P.moves.length / 2);
const solverDone = () => Math.ceil(step / 2);

function renderSteps() {
  const total = solverMoves(), done = state === 'done' ? total : solverDone();
  $('#puzzle-steps').innerHTML = total < 2 ? '' : Array.from({ length: total }, (_, i) =>
    `<i class="${i < done ? 'done' : ''} ${i === done && state !== 'done' ? 'current' : ''}"></i>`).join('')
    + `<span>${state === 'done' ? `${total} moves` : `Move ${Math.min(done + 1, total)} of ${total}`}</span>`;
}

function renderInfo() {
  let html = '';
  if (P.kind === 'train') {
    // the themes would give the answer away, so they only show once it is solved
    if (state === 'done') {
      const names = P.themes.map(t => THEME_NAMES[t]).filter(Boolean).slice(0, 4);
      html = names.map(n => `<span class="tag">${n}</span>`).join('');
    }
  } else {
    html = `<span class="pill">${badgeSVG(P.cls, 16)} ${escapeHtml(P.played)}</span>
      <span>vs ${escapeHtml(P.opponent)}${P.date ? ` · ${P.date}` : ''} · move ${P.move_number}</span>
      <a href="/review/${P.game_id}?ply=${P.ply}">Open in review</a>`;
  }
  $('#puzzle-info').innerHTML = html;
  // results of this visit; nothing to show before the first one is finished
  $('#puzzle-progress').innerHTML = !session.length ? '' : session.slice(-40).map(o => `<i class="${o === 'failed' ? 'failed' : 'solved'}"></i>`).join('')
    + (state === 'done' ? '' : '<i class="current"></i>');
}

function renderButtons() {
  const solving = state === 'solving';
  $('#btn-hint').disabled = !solving || hintLevel >= 2;
  $('#btn-hint').textContent = hintLevel === 1 ? 'Show the move' : 'Hint';
  $('#btn-solution').disabled = state === 'done' || state === 'idle';
  const last = source === 'games' && index >= queue.length - 1;
  $('#btn-next').disabled = last && state !== 'idle';
  $('#btn-next').textContent = state === 'done' ? 'Next puzzle' : 'Skip';
  $('#btn-next').classList.toggle('btn-primary', state === 'done');
}

function renderRating(delta = 0) {
  $('#rating-card').hidden = source !== 'train';
  if (source !== 'train') return;
  const sign = delta > 0 ? `<span class="pr-delta up">+${delta}</span>` : delta < 0 ? `<span class="pr-delta down">${delta}</span>` : '';
  $('#pr-value').innerHTML = `${rating ?? '–'}${sign}`;
  $('#pr-streak').textContent = totals.streak;
  $('#pr-solved').textContent = totals.solved;
  const played = totals.solved + totals.failed;
  $('#pr-rate').textContent = played ? `${Math.round((100 * totals.solved) / played)}%` : '–';
}

function renderFocus() {
  const card = $('#focus-card');
  card.hidden = source !== 'train' || !train;
  if (card.hidden) return;
  const p = train.profile;
  $('#focus-note').textContent = p.errors
    ? `Based on the ${p.errors} serious errors in your last ${p.games} reviewed game${p.games === 1 ? '' : 's'}. The puzzles are not from those games: they train the same patterns.`
    : (username ? 'Review some of your games and I will lean the puzzles toward what you get wrong. For now it is an even mix.'
                : 'Link your chess.com account and review some games: I will lean the puzzles toward what you get wrong. For now it is an even mix.');
  $('#focus-top').textContent = p.focus[0].label;
  $('#focus-list').innerHTML = p.focus.map(f => `<div class="focus-row ${P && P.focus === f.id && state === 'done' ? 'on' : ''}">
      <div class="focus-top"><b>${escapeHtml(f.label)}</b><span class="muted">${f.share}% of puzzles</span></div>
      <div class="bar"><div class="bar-fill" style="width:${Math.min(100, f.share * 2.2)}%"></div></div>
      ${f.reason ? `<div class="muted focus-why">${escapeHtml(f.reason)}</div>` : ''}</div>`).join('');
}

function renderAll() { renderSteps(); renderInfo(); renderButtons(); saveState(); }

// ================================================================== playing
/** Play a UCI move of the line on the board (with sound). Returns the chess.js move. */
function push(uci) {
  const [from, to] = squares(uci);
  const move = game.move({ from, to, promotion: uci[4] || undefined });
  playMoveSound(move.san);
  return move;
}

function sideToMove() { return game.turn() === 'w' ? 'White' : 'Black'; }

function prompt() {
  state = 'solving';
  hintLevel = 0;
  const lastUci = step > 0 ? P.moves[step - 1] : P.lead;
  setBoard({ last: lastUci ? squares(lastUci) : null, interactive: true });
  if (step === 0) {
    const n = solverMoves();
    let text;
    if (P.kind === 'games') text = `In the game you played ${P.played}, ${CLS[P.cls].article}. Can you find the best move?`;
    else if (n === 1) text = 'One move decides it. Find it!';
    else text = `Find the best move. The line is ${n} moves long: I'll answer for your opponent after each one.`;
    setCoach('thinking', null, `${sideToMove()} to move`, text);
  }
  renderAll();
}

/** Put a puzzle back where it was left (after a reload): replay the moves already made. */
function resumePuzzle(saved) {
  P = queue[index];
  token += 1;
  game = new Chess(P.fen);
  hintLevel = 0;
  outcome = saved.outcome || null;
  session = saved.session || [];
  const replay = uci => game.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] || undefined });
  if (P.lead) replay(P.lead);
  // an odd step means the opponent's reply was still pending: go back to the user's move
  step = Math.min(saved.step - (saved.step % 2 && saved.step < P.moves.length ? 1 : 0), P.moves.length);
  for (const uci of P.moves.slice(0, step)) replay(uci);
  renderFocus();
  if (step >= P.moves.length) {
    session.pop();                                    // finish() records the outcome again
    finish(squares(P.moves[P.moves.length - 1]));
    return;
  }
  prompt();
  if (step > 0) setCoach('thinking', null, `${sideToMove()} to move`, 'Find the best move.');
}

function showPuzzle() {
  P = queue[index];
  token += 1;
  const mine = token;
  game = new Chess(P.fen);
  step = 0; hintLevel = 0; outcome = null;
  renderFocus();
  if (!P.lead) { prompt(); return; }
  // Show the position, then the opponent's move that sets up the puzzle
  state = 'lead';
  setBoard();
  setCoach('thinking', null, 'Watch the last move', 'Your opponent is about to move…');
  renderAll();
  setTimeout(() => {
    if (mine !== token) return;
    push(P.lead);
    prompt();
  }, 700);
}

/** Record the result of the puzzle once (first mistake, help, or clean solve). */
function settle(result) {
  if (outcome) return 0;
  outcome = result;
  if (source !== 'train') return 0;
  remember(P.id);
  let delta = 0;
  if (result !== 'helped') {                       // a hint neither wins nor loses points
    const expected = 1 / (1 + 10 ** ((P.rating - rating) / 400));
    delta = Math.round(train.k * ((result === 'solved' ? 1 : 0) - expected));
    if (result === 'solved' && delta < 1) delta = 1;
    const [lo, hi] = train.rating_range;
    rating = Math.max(lo, Math.min(hi, rating + delta));
    store.set('puzzleRating', String(rating));
  }
  if (result === 'solved') {
    totals.solved += 1; totals.streak += 1; totals.best = Math.max(totals.best, totals.streak);
  } else if (result === 'failed') {
    totals.failed += 1; totals.streak = 0;
  }
  store.set('puzzleStats', JSON.stringify(totals));
  renderRating(delta);
  return delta;
}

function finish(last) {
  state = 'done';
  const delta = settle('solved');                   // no-op when it was already failed / helped
  session.push(outcome);
  setBoard({ last, cls: 'best' });
  const line = P.kind === 'games' && P.line ? `Line: <b>${escapeHtml(P.line.join(' '))}</b> <span>(${P.eval})</span>` : '';
  if (outcome === 'solved') {
    const streak = source === 'train' && totals.streak >= 3 ? ` That's ${totals.streak} in a row.` : '';
    setCoach('surprised', 'best', 'Solved!', (delta > 0 ? `Clean solve: +${delta} rating.` : 'You found every move.') + streak, line);
  } else if (outcome === 'helped') {
    setCoach('happy', 'best', 'Solved with a hint', 'You got there. Next time try to find it without the hint.', line);
  } else {
    setCoach('happy', 'best', 'That was the line', 'Play it through once more in your head, then try the next one.', line);
  }
  renderAll();
  renderFocus();
  maybeLoadMore();
}

/** The opponent answers, then it is the user's turn again. */
function opponentReply() {
  state = 'reply';
  renderButtons();
  const mine = token;
  setTimeout(() => {
    if (mine !== token) return;
    push(P.moves[step]);
    step += 1;
    prompt();
    const reply = game.history().slice(-1)[0];
    setCoach('thinking', null, `${reply} — keep going`, `Good move! Your opponent answered ${reply}. What now?`);
  }, REPLY_DELAY_MS);
}

function onUserMove(orig, dest) {
  if (state !== 'solving') return;
  const expected = P.moves[step];
  const probe = new Chess(game.fen());
  const played = tryMove(probe, orig, dest);
  if (!played) { setBoard({ interactive: true, hint: hintLevel }); return; }
  const uci = played.from + played.to;
  const alsoGood = (P.good || []).some(g => g.slice(0, 4) === uci);
  // any checkmate solves a mating puzzle, even if it is not the listed move
  const correct = uci === expected.slice(0, 4) || alsoGood || probe.isCheckmate();
  if (!correct) {
    settle('failed');
    playMoveSound(played.san);
    state = 'reply';                                  // locks the board while the move is shown
    const before = game;
    game = probe;
    setBoard({ last: [played.from, played.to], cls: 'mistake' });
    game = before;
    setCoach('worried', 'mistake', `${played.san}?`,
      P.kind === 'games' && played.san === P.played ? "That's what you played in the game. Try something else!"
        : 'Not this one. Look again: what is attacked, what is undefended, is there a check?');
    renderAll();
    const mine = token, level = hintLevel;
    setTimeout(() => {
      if (mine !== token) return;
      state = 'solving';
      const lastUci = step > 0 ? P.moves[step - 1] : P.lead;
      setBoard({ last: lastUci ? squares(lastUci) : null, interactive: true, hint: level });
      renderAll();
    }, 900);
    return;
  }
  // Correct: play it (with the line's own promotion piece when it is the listed move)
  const exact = uci === expected.slice(0, 4);
  const move = game.move({ from: played.from, to: played.to, promotion: exact && expected[4] ? expected[4] : 'q' });
  playMoveSound(move.san);
  step += 1;
  const last = [move.from, move.to];
  if (!exact || step >= P.moves.length || game.isGameOver()) { finish(last); return; }
  setBoard({ last, cls: 'best' });
  renderSteps();
  opponentReply();
}

function hint() {
  if (state !== 'solving' || hintLevel >= 2) return;
  if (outcome !== 'failed') settle('helped');
  hintLevel += 1;
  const [from, to] = squares(P.moves[step]);
  const piece = PIECE_NAMES[game.get(from).type];
  const lastUci = step > 0 ? P.moves[step - 1] : P.lead;
  setBoard({ last: lastUci ? squares(lastUci) : null, interactive: true, hint: hintLevel });
  if (hintLevel === 1) setCoach('thinking', null, `Hint: the ${piece}`, `The ${piece} on ${from} is the piece to move. Where does it do the most damage? Ask again and I'll show you.`);
  else setCoach('thinking', null, `Hint: ${piece} to ${to}`, 'Follow the arrow, and think about why it works before you play it.');
  renderButtons();
}

/** Play the rest of the line on the board, one move at a time. */
function showSolution() {
  if (state === 'done' || state === 'idle') return;
  settle('failed');
  token += 1;
  const mine = token;
  state = 'reply';
  setBoard();
  renderButtons();
  const sans = [];
  const next = () => {
    if (mine !== token) return;
    if (step >= P.moves.length) { finish(squares(P.moves[P.moves.length - 1])); return; }
    const move = push(P.moves[step]);
    sans.push(move.san);
    step += 1;
    setBoard({ last: [move.from, move.to], cls: step % 2 === 1 ? 'best' : 'plain' });
    setCoach('happy', 'best', 'The solution', sans.join(' '));
    renderSteps();
    setTimeout(next, 950);
  };
  next();
}

function nextPuzzle() {
  if ($('#btn-next').disabled) return;
  if (state !== 'done' && P && source === 'train') remember(P.id);     // skipped: do not serve it again
  if (index < queue.length - 1) { index += 1; showPuzzle(); maybeLoadMore(); return; }
  if (source === 'train') loadTraining(true).then(showPuzzle).catch(e => setCoach('worried', null, 'No more puzzles', e.message));
}

// ================================================================== loading
function ensureBoard() {
  if (cg) return;
  cg = Chessground($('#board'), {
    coordinates: true,
    animation: { enabled: true, duration: 220 },
    movable: { free: false, showDests: true, events: { after: onUserMove } },
    premovable: { enabled: false },
    drawable: { enabled: true, visible: true },
  });
  window.addEventListener('resize', () => cg.redrawAll());
  document.addEventListener('settingschange', () => cg.redrawAll());
}

async function fetchTraining() {
  const { data } = await api('/api/puzzles/train', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating, seen: [...seen, ...queue.map(p => p.id)] }),
  });
  train = data;
  if (rating === null) { rating = data.rating; store.set('puzzleRating', String(rating)); }
  return data.puzzles.map(p => ({ ...p, kind: 'train' }));
}

/** Top the queue up in the background when it is about to run out. */
async function maybeLoadMore() {
  if (source !== 'train' || loadingMore || queue.length - index > 3) return;
  loadingMore = true;
  try { queue.push(...await fetchTraining()); } catch (e) { /* try again on the next puzzle */ }
  loadingMore = false;
  renderButtons();
}

async function loadTraining(advance = false) {
  const more = await fetchTraining();
  if (advance) { queue.push(...more); if (index < queue.length - 1) index += 1; }
  else { queue = more; index = 0; }
}

async function loadGames() {
  const { data } = await api(`/api/puzzles/${encodeURIComponent(username)}?n=50`);
  queue = data.puzzles.map(p => ({
    ...p, kind: 'games', lead: null, moves: [p.best_uci], good: p.good_moves, themes: [],
  }));
  index = 0;
}

async function load() {
  const error = $('#puzzle-error'), empty = $('#puzzle-empty'), stage = $('#puzzle-stage');
  token += 1;
  state = 'idle';
  error.hidden = true; empty.hidden = true;
  for (const b of document.querySelectorAll('#puzzle-source [data-source]')) b.classList.toggle('on', b.dataset.source === source);
  $('#puzzle-who').textContent = source === 'train'
    ? 'Multi-move puzzles, picked for the patterns you miss most in your own games.'
    : 'Every blunder and miss you played, as a find-the-best-move puzzle.';
  session = [];
  if (source === 'games' && !username) {
    stage.hidden = true; empty.hidden = false;
    empty.innerHTML = 'Link your chess.com account to get puzzles from your own games. <a class="btn btn-small btn-primary" href="/settings#account">Link account</a>';
    return;
  }
  // Same tab, same source (a reload, or the language was switched): carry on where it was
  const saved = savedState();
  try {
    if (saved) {
      queue = saved.queue; index = 0;
      if (source === 'train') { train = (await api('/api/puzzles/train', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rating, n: 1, seen }) })).data; }
    } else if (source === 'train') await loadTraining(); else await loadGames();
  } catch (e) {
    error.textContent = e.message; error.hidden = false; stage.hidden = true;
    return;
  }
  if (!queue.length) {
    stage.hidden = true; empty.hidden = false;
    empty.innerHTML = source === 'train'
      ? 'The puzzle bank is missing. Build it with <code>python scripts/build_puzzles.py</code> (see the README).'
      : 'No puzzles yet. Review some of your games first (or analyse a batch from the <a href="/stats">Stats</a> page): every blunder and miss you played becomes a puzzle.';
    return;
  }
  stage.hidden = false;
  ensureBoard();
  renderRating();
  if (saved) resumePuzzle(saved); else showPuzzle();
}

// ================================================================= controls
$('#btn-hint').addEventListener('click', hint);
$('#btn-solution').addEventListener('click', showSolution);
$('#btn-next').addEventListener('click', nextPuzzle);
$('#puzzle-source').addEventListener('click', e => {
  const button = e.target.closest('[data-source]');
  if (!button || button.dataset.source === source) return;
  source = button.dataset.source;
  store.set('puzzleSource', source);
  try { sessionStorage.removeItem('puzzleState'); } catch (err) { /* nothing saved */ }
  load();
});
document.addEventListener('keydown', e => {
  if (!P || e.metaKey || e.ctrlKey || e.altKey) return;
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
  const actions = { h: hint, H: hint, n: nextPuzzle, N: nextPuzzle, ArrowRight: () => { if (state === 'done') nextPuzzle(); } };
  if (actions[e.key]) { e.preventDefault(); actions[e.key](); }
});

load();

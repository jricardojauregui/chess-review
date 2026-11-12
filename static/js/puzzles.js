// "Puzzles from my mistakes": every Blunder / Miss becomes a find-the-best-move puzzle.
import { Chessground } from '../vendor/chessground.min.js';
import { Chess } from '../vendor/chess.js';
import {
  $, CLS, accountName, api, badgeSVG, escapeHtml, legalDests, playMoveSound, showCoach, squareXY, tryMove,
} from './common.js';

let puzzles = [];
let index = 0;
let cg = null;
let status = {};      // puzzle id -> 'solved' | 'failed'
let locked = false;   // true once the current puzzle is solved / revealed

const username = accountName();
$('#puzzle-who').textContent = username ? 'Every blunder and miss you played, turned into a find-the-best-move puzzle.' : '';

function setCoach(expression, cls, title, text, line = '') {
  showCoach($('#coach-avatar'), expression);
  $('#bubble-icon').innerHTML = cls ? badgeSVG(cls, 24) : '';
  $('#bubble-title').textContent = title;
  $('#bubble-text').textContent = text;
  $('#bubble-line').innerHTML = line;
  const bubble = $('#bubble');
  bubble.classList.remove('pop'); void bubble.offsetWidth; bubble.classList.add('pop');
}

function setBoard(p, { fen, lastMove, cls, interactive }) {
  const orientation = p.color === 'w' ? 'white' : 'black';
  const custom = new Map();
  if (lastMove && cls) for (const sq of lastMove) custom.set(sq, `hl-${cls}`);
  const game = new Chess(fen);
  cg.set({
    fen, orientation,
    turnColor: fen.split(' ')[1] === 'w' ? 'white' : 'black',
    lastMove: lastMove || undefined,
    check: game.inCheck(),
    highlight: { lastMove: false, check: true, custom },
    movable: { color: interactive ? orientation : undefined, dests: interactive ? legalDests(game) : new Map() },
    drawable: { autoShapes: [] },
  });
  const badge = $('#move-badge');
  if (lastMove && cls) {
    const { x, y } = squareXY(lastMove[1], orientation);
    badge.style.left = `${(x + 1) * 12.5}%`;
    badge.style.top = `${y * 12.5}%`;
    badge.innerHTML = badgeSVG(cls, 32);
    badge.hidden = false;
  } else badge.hidden = true;
}

function renderProgress() {
  $('#puzzle-progress').innerHTML = puzzles.map((p, i) =>
    `<i class="${status[p.id] || ''} ${i === index ? 'current' : ''}"></i>`).join('');
}

function showPuzzle() {
  const p = puzzles[index];
  locked = false;
  setBoard(p, { fen: p.fen, interactive: true });
  const side = p.color === 'w' ? 'White' : 'Black';
  setCoach('thinking', null, `${side} to move`,
    `In the game you played ${p.played}, a ${CLS[p.cls].label.toLowerCase()}. Can you find the best move?`);
  $('#puzzle-info').innerHTML =
    `<span class="pill">Puzzle ${index + 1} / ${puzzles.length}</span>
     <span class="pill">${badgeSVG(p.cls, 16)} ${escapeHtml(p.played)}</span>
     <span>vs ${escapeHtml(p.opponent)}${p.date ? ` · ${p.date}` : ''} · move ${p.move_number}</span>
     <a href="/review/${p.game_id}?ply=${p.ply}">Open in review</a>`;
  $('#btn-prev').disabled = index === 0;
  $('#btn-next').disabled = index >= puzzles.length - 1;
  $('#btn-solution').disabled = false;
  renderProgress();
}

function reveal(p, solvedByUser, sanPlayed) {
  locked = true;
  const game = new Chess(p.fen);
  const from = p.best_uci.slice(0, 2), to = p.best_uci.slice(2, 4);
  if (!sanPlayed) { game.move({ from, to, promotion: p.best_uci[4] || undefined }); playMoveSound(p.best); }
  const line = `Line: <b>${escapeHtml(p.line.join(' '))}</b> <span>(${p.eval})</span>`;
  if (solvedByUser) {
    status[p.id] = status[p.id] || 'solved';
    setCoach('surprised', 'best', `${sanPlayed} — correct!`,
      sanPlayed === p.best ? `That's it! ${p.best} was the move to find.`
                           : `Yes! ${sanPlayed} is just as strong as ${p.best}.`, line);
  } else {
    status[p.id] = 'failed';
    setBoard(p, { fen: game.fen(), lastMove: [from, to], cls: 'best', interactive: false });
    setCoach('happy', 'best', `${p.best} was best`, `Here it is: ${p.best}. Play through the line and try the next one.`, line);
  }
  $('#btn-solution').disabled = true;
  renderProgress();
}

function onUserMove(orig, dest) {
  if (locked) return;
  const p = puzzles[index];
  const game = new Chess(p.fen);
  const played = tryMove(game, orig, dest);
  if (!played) { showPuzzle(); return; }
  playMoveSound(played.san);
  const uci = played.from + played.to + (played.promotion || '');
  const good = p.good_moves.some(g => g === uci || (g.length === 4 && g === uci.slice(0, 4)));
  if (good) {
    setBoard(p, { fen: game.fen(), lastMove: [played.from, played.to], cls: 'best', interactive: false });
    reveal(p, true, played.san);
    return;
  }
  status[p.id] = 'failed';
  setBoard(p, { fen: game.fen(), lastMove: [played.from, played.to], cls: 'mistake', interactive: false });
  setCoach('worried', 'mistake', `${played.san}?`,
    played.san === p.played ? "That's what you played in the game. Try something else!" : 'Not quite. Try again!');
  renderProgress();
  setTimeout(() => { if (!locked && puzzles[index] === p) setBoard(p, { fen: p.fen, interactive: true }); }, 900);
}

async function load() {
  const error = $('#puzzle-error'), empty = $('#puzzle-empty'), stage = $('#puzzle-stage');
  error.hidden = true; empty.hidden = true;
  if (!username) {
    empty.hidden = false;
    empty.innerHTML = 'Link your chess.com account to get puzzles from your own games. <a class="btn btn-small btn-primary" href="/settings#account">Link account</a>';
    return;
  }
  try {
    const { data } = await api(`/api/puzzles/${encodeURIComponent(username)}?n=50`);
    puzzles = data.puzzles;
  } catch (e) {
    error.textContent = e.message; error.hidden = false; stage.hidden = true;
    return;
  }
  if (!puzzles.length) {
    stage.hidden = true;
    empty.hidden = false;
    empty.innerHTML = 'No puzzles yet. Review some of your games first (or analyse a batch from the <a href="/stats">Stats</a> page): every blunder and miss you played becomes a puzzle.';
    return;
  }
  stage.hidden = false;
  index = 0; status = {};
  if (!cg) {
    cg = Chessground($('#board'), {
      coordinates: true,
      animation: { enabled: true, duration: 220 },
      movable: { free: false, showDests: true, events: { after: onUserMove } },
      premovable: { enabled: false },
    });
    window.addEventListener('resize', () => cg.redrawAll());
    document.addEventListener('settingschange', () => cg.redrawAll());
  }
  showPuzzle();
}

$('#btn-prev').addEventListener('click', () => { if (index > 0) { index--; showPuzzle(); } });
$('#btn-next').addEventListener('click', () => { if (index < puzzles.length - 1) { index++; showPuzzle(); } });
$('#btn-solution').addEventListener('click', () => reveal(puzzles[index], false));
load();

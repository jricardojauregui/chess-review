// One opening lesson, in three steps:
//   1. a guided lesson of the main line (the coach shows every move, you play it),
//   2. practice from memory, with two-step hints (the piece, then the move),
//   3. the extra lines, which unlock once the main line is learned.
import { Chessground } from '../vendor/chessground.min.js';
import { Chess } from '../vendor/chess.js';
import {
  $, api, drawArrows, escapeHtml, legalDests, playMoveSound, showCoach, store, toast, tryMove,
} from './common.js';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const lessonId = $('#app').dataset.lessonId;

let L = null;               // lesson from the server
let cg = null;
let lineIdx = 0;            // 0 = main line, then the extra lines
let ply = 0;                // 0 = starting position, n = after the n-th move of the line
let orientation = 'white';
// browse:   step freely through the line with the coach's comments
// learn:    the guided lesson: the coach shows each of your moves and you play it
// practice: you play the line from memory (hints: first the piece, then the move)
let mode = 'browse';
let waiting = null;         // learn: 'start' | 'move' (yours) | 'continue' (after a reply)
let hintLevel = 0;          // practice: 0 none, 1 piece highlighted, 2 arrow shown
let token = 0;              // cancels pending timers when the state changes
let playTimer = null;

const plies = () => L.lines[lineIdx].plies;
const fenAt = p => (p > 0 ? plies()[p - 1].fen : START_FEN);
const label = m => `${m.move_number}${m.color === 'w' ? '.' : '...'} ${m.san}`;
const sideName = c => (c === 'w' ? 'White' : 'Black');
const squares = uci => [uci.slice(0, 2), uci.slice(2, 4)];
const PIECE_NAMES = { p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen', k: 'king' };

// ------------------------------------------------------------ saved progress
// openingsTutorial: guided lessons finished; openingsLines: lines played from
// memory; openingsLearned: lessons whose main line was played from memory.
function saved(key) {
  try { return JSON.parse(store.get(key, '{}')) || {}; } catch (e) { return {}; }
}
function mark(key, value) {
  const all = saved(key);
  all[L.id] = value === true ? true : { ...(all[L.id] || {}), ...value };
  store.set(key, JSON.stringify(all));
}
const tutorialDone = () => saved('openingsTutorial')[L.id] || {};
const practiceDone = () => saved('openingsLines')[L.id] || {};
/** The extra lines open up once the main line has been learned. */
const extrasUnlocked = () => Boolean(tutorialDone()[0] || practiceDone()[0]);

// ==================================================================== boot
async function boot() {
  showCoach($('#loading-coach'), 'thinking');
  try {
    L = (await api(`/api/openings/lesson/${encodeURIComponent(lessonId)}`)).data;
  } catch (e) {
    showCoach($('#loading-coach'), 'worried');
    $('#loading-title').textContent = 'Could not open this lesson';
    $('#loading-error').textContent = e.message;
    $('#loading-error').hidden = false;
    $('#loading-back').hidden = false;
    return;
  }
  document.title = `${L.name} · Chess Review`;
  orientation = L.side === 'b' ? 'black' : 'white';
  $('#stage-loading').hidden = true;
  $('#stage-main').hidden = false;
  cg = Chessground($('#board'), {
    fen: START_FEN, orientation, coordinates: true,
    animation: { enabled: true, duration: 220 },
    highlight: { lastMove: false, check: true },
    movable: { free: false, color: undefined, showDests: true, events: { after: onUserMove } },
    premovable: { enabled: false }, draggable: { showGhost: true },
    drawable: { enabled: true, visible: true },
  });
  window.addEventListener('resize', () => cg.redrawAll());
  document.addEventListener('settingschange', () => cg.redrawAll());
  renderStatic();
  // New lesson: start from the first move, ready for the guided lesson.
  // Already learned: open on the position that gives the opening its name.
  goTo(tutorialDone()[0] ? Math.min(L.signature_plies, plies().length) : 0, { silent: true });
}

// ========================================================== static content
function wdlHTML(t) {
  return `<div class="wdl">${t.win ? `<span class="w" style="flex:${t.win}"></span>` : ''}${t.draw ? `<span class="d" style="flex:${t.draw}"></span>` : ''}${t.loss ? `<span class="l" style="flex:${t.loss}"></span>` : ''}</div>`;
}

function gamesBlock(title, tally, recent) {
  if (!tally.games) return '';
  const rows = recent.map(g => `<a class="named-row" href="/review/${g.id}">
      <span class="outcome ${g.outcome}">${{ win: 'W', loss: 'L', draw: 'D' }[g.outcome] || '–'}</span>
      <b>vs ${escapeHtml(g.opponent || '?')}</b><span class="muted">${g.opponent_rating ? `(${g.opponent_rating}) · ` : ''}${g.date || ''}</span></a>`).join('');
  return `<div class="games-block">
      <div class="gb-head"><b>${title}</b><span class="muted">${tally.games} game${tally.games === 1 ? '' : 's'} · ${tally.win}W ${tally.draw}D ${tally.loss}L${tally.score === null ? '' : ` · you score ${tally.score}%`}</span></div>
      ${wdlHTML(tally)}${rows}</div>`;
}

function renderStatic() {
  $('#lesson-name').textContent = L.name;
  const tags = [`<span class="tag">${L.eco}</span>`,
    `<span class="tag"><span class="piece-dot ${L.side}"></span>For ${sideName(L.side)}</span>`];
  if (L.level_name) tags.push(`<span class="tag level-${L.level}">${L.level_name}</span>`);
  for (const t of L.tags || []) tags.push(`<span class="tag">${escapeHtml(t)}</span>`);
  $('#lesson-tags').innerHTML = tags.join('');

  if (L.curated) {
    $('#why-body').innerHTML = `<p>${escapeHtml(L.why)}</p>
      <div class="sub-title">The ideas to remember</div>
      <ul class="ideas">${L.ideas.map(i => `<li>${escapeHtml(i)}</li>`).join('')}</ul>
      <div class="watch-out"><b>Watch out.</b> ${escapeHtml(L.watch)}</div>`;
  } else {
    $('#why-title').textContent = 'About this line';
    const parent = L.parent
      ? `<p>It is a branch of the <a href="/openings/${L.parent.id}"><b>${escapeHtml(L.parent.name)}</b></a>: open that lesson for the plans, the typical mistakes and my full explanation.</p>` : '';
    $('#why-body').innerHTML = `${parent}<p class="muted">This line comes from the opening database. My comments here follow general opening principles (development, the centre, king safety) rather than a lesson written for it.</p>`;
  }

  const other = L.side === 'w' ? 'b' : 'w';
  const blocks = gamesBlock(`You, as ${sideName(L.side)}`, L.plays, L.recent.plays)
    + gamesBlock(`Against you, as ${sideName(other)}`, L.faces, L.recent.faces);
  $('#games-body').innerHTML = blocks || '<div class="muted">None of your stored games went into this opening yet.</div>';

  if (L.named.length) {
    $('#named-card').hidden = false;
    $('#named-title').textContent = `Named variations (${L.named.length}${L.named.length >= 40 ? '+' : ''})`;
    $('#named-list').innerHTML = L.named.map(n => `<a class="named-row" href="/openings/${n.id}">
      <span class="tag">${n.eco}</span><b>${escapeHtml(n.name.replace(`${L.name_en || L.name}: `, ''))}</b><span class="muted">${escapeHtml(n.moves)}</span></a>`).join('');
  }
  renderLines();
}

function renderLines() {
  const learned = tutorialDone(), played = practiceDone();
  const open = extrasUnlocked();
  const extra = L.lines.length - 1;
  $('#line-choice').hidden = L.lines.length < 2;
  // Extra lines stay out of the way until the main line is learned
  $('#line-choice').innerHTML = L.lines.map((line, i) => (i > 0 && !open ? '' :
    `<button type="button" class="pill-choice ${i === lineIdx ? 'on' : ''}" data-line="${i}">${played[i] ? '<span class="pc-state" title="Played from memory">✓✓</span>' : learned[i] ? '<span class="pc-state" title="Guided lesson done">✓</span>' : ''}${escapeHtml(line.name)}</button>`)).join('');
  $('#lines-locked').hidden = open || extra < 1;
  $('#lines-locked').textContent = `Finish the guided lesson of the main line to unlock ${extra} extra line${extra === 1 ? '' : 's'}.`;
  renderMoves();
}

function renderMoves() {
  const line = L.lines[lineIdx];
  // In a lesson or practice, the moves you have not reached yet stay hidden
  const visible = mode === 'browse' ? line.plies.length : ply;
  let html = '';
  line.plies.slice(0, visible).forEach((m, i) => {
    if (m.color === 'w') html += `<div class="no">${m.move_number}.</div>`;
    html += `<button class="mv ${i < line.start ? 'shared' : ''} ${i + 1 === ply ? 'current' : ''}" data-ply="${i + 1}"><span>${escapeHtml(m.san)}</span></button>`;
  });
  $('#moves').innerHTML = html;
  const active = $('#moves .mv.current');
  if (active) active.scrollIntoView({ block: 'nearest' });
}

// ============================================================== rendering
function setCoach(expression, title, text) {
  showCoach($('#coach-avatar'), expression);
  $('#bubble-title').textContent = title || '';
  $('#bubble-text').textContent = text || '';
  const bubble = $('#bubble');
  bubble.classList.remove('pop'); void bubble.offsetWidth; bubble.classList.add('pop');
}

/**
 * Put the position after `p` plies on the board.
 * hint: 0 nothing, 1 the piece of the next move in blue, 2 also the arrow.
 */
function setBoard(p, { cls = 'book', movable = false, hint = 0 } = {}) {
  const fen = fenAt(p);
  const game = new Chess(fen);
  const last = p > 0 ? squares(plies()[p - 1].uci) : null;
  const custom = new Map();
  if (last) for (const sq of last) custom.set(sq, `hl-${cls}`);
  const arrows = [];
  if (hint >= 1 && plies()[p]) {
    const [from, to] = squares(plies()[p].uci);
    custom.set(from, 'mark-hint');
    if (hint >= 2) arrows.push({ orig: from, dest: to, kind: 'hint' });
  }
  const turn = fen.split(' ')[1] === 'w' ? 'white' : 'black';
  cg.set({
    fen, orientation, turnColor: turn, lastMove: last || undefined, check: game.inCheck(),
    highlight: { lastMove: false, check: true, custom },
    movable: { color: movable ? turn : undefined, dests: movable ? legalDests(game) : new Map() },
    drawable: { autoShapes: [] },
  });
  cg.setShapes([]);
  drawArrows($('#arrows'), arrows, orientation);
}

/** Buttons, progress bar and move list for the current mode. */
function renderChrome() {
  const line = L.lines[lineIdx], n = line.plies.length;
  const busy = mode !== 'browse';
  $('#btn-exit').hidden = !busy;
  $('#btn-exit').textContent = mode === 'learn' ? 'Exit lesson' : 'Stop practice';
  $('#btn-hint').hidden = mode !== 'practice';
  $('#btn-hint').disabled = hintLevel >= 2 || !plies()[ply] || plies()[ply].color !== L.side;
  $('#btn-hint').textContent = hintLevel === 1 ? 'Show the move' : 'Hint';
  $('#btn-practice').hidden = busy;
  const main = $('#btn-main');
  main.hidden = mode === 'practice';
  main.disabled = false;
  if (mode === 'learn') {
    main.textContent = { start: 'Start', move: 'Play it for me', continue: 'Continue' }[waiting] || 'Continue';
    main.disabled = !waiting;
  } else {
    main.textContent = tutorialDone()[lineIdx] ? 'Repeat the guided lesson' : 'Start guided lesson';
  }
  // the next thing to do is the highlighted button: lesson first, then practice
  const practiceNext = !busy && Boolean(tutorialDone()[lineIdx]) && !practiceDone()[lineIdx];
  $('#btn-practice').classList.toggle('btn-primary', practiceNext);
  main.classList.toggle('btn-primary', !practiceNext);
  for (const id of ['#nav-first', '#nav-prev', '#nav-next', '#nav-last', '#nav-play']) $(id).disabled = busy;
  if (!busy) {
    $('#nav-next').disabled = $('#nav-last').disabled = ply >= n;
    $('#nav-prev').disabled = $('#nav-first').disabled = ply <= 0;
  }
  // progress through the line (from where the lesson starts)
  const from = mode === 'learn' ? (line.start || 0) : 0;
  $('#lesson-progress').hidden = !busy;
  $('#lp-fill').style.width = `${Math.round((100 * Math.max(0, ply - from)) / Math.max(1, n - from))}%`;
  $('#lp-label').textContent = `Move ${Math.max(0, ply - from)} of ${n - from}`;
  renderMoves();
}

/** Browse mode: show the current move of the line with the coach's explanation. */
function render() {
  const line = L.lines[lineIdx], n = line.plies.length;
  setBoard(ply);
  if (ply === 0) {
    const first = !tutorialDone()[0];
    setCoach('happy', L.name, first
      ? `${L.curated ? `${L.tagline} ` : ''}Press Start guided lesson: I'll show you every move, you play it on the board, and I'll explain what it is for.`
      : 'Step through the moves with the arrows, repeat the guided lesson, or practice the line from memory.');
  } else {
    const m = line.plies[ply - 1];
    const mine = m.color === L.side;
    let text = m.comment;
    if (ply === n) text += ' End of this line.';
    setCoach(ply === n ? 'happy' : (mine ? 'happy' : 'thinking'), label(m), text);
  }
  renderChrome();
}

function goTo(target, { silent = false, auto = false } = {}) {
  if (mode !== 'browse') return;
  if (!auto) stopPlay();
  const next = Math.max(0, Math.min(plies().length, target));
  if (!silent) {
    if (next === ply + 1) playMoveSound(plies()[next - 1].san);
    else if (next === ply - 1) playMoveSound(plies()[ply - 1].san);
  }
  ply = next;
  render();
}

function chooseLine(index) {
  leaveMode();
  stopPlay();
  lineIdx = index;
  // An extra line opens where it leaves the main line
  ply = Math.min(L.lines[index].start || (tutorialDone()[index] ? L.signature_plies : 0), plies().length);
  renderLines();
  render();
}

/** Back to browse mode (without redrawing). */
function leaveMode() {
  mode = 'browse';
  waiting = null;
  hintLevel = 0;
  token += 1;
}

// ================================================================ autoplay
function paintPlay() {
  const button = $('#nav-play'), playing = playTimer !== null;
  button.classList.toggle('playing', playing);
  button.setAttribute('aria-pressed', String(playing));
  button.title = playing ? 'Pause (Space)' : 'Play the line (Space)';
}
function stopPlay() {
  if (playTimer === null) return;
  clearInterval(playTimer);
  playTimer = null;
  paintPlay();
}
function togglePlay() {
  if (mode !== 'browse') return;
  if (playTimer !== null) { stopPlay(); return; }
  if (ply >= plies().length) goTo(0, { silent: true, auto: true });
  // slow enough to read the explanation of each move
  playTimer = setInterval(() => {
    if (ply >= plies().length) { stopPlay(); return; }
    goTo(ply + 1, { auto: true });
    if (ply >= plies().length) stopPlay();
  }, 3200);
  paintPlay();
}

// =========================================================== guided lesson
// Step by step: on your moves the coach explains the move and shows it (blue
// piece + arrow) and you play it on the board; the other side's replies are
// played for you, explained, and you press Continue.
function startLearn() {
  stopPlay();
  leaveMode();
  mode = 'learn';
  const line = L.lines[lineIdx];
  ply = line.start || 0;
  waiting = 'start';
  setBoard(ply);
  const other = sideName(L.side === 'w' ? 'b' : 'w');
  setCoach('happy', `Guided lesson: ${lineIdx === 0 ? L.name : line.name}`, ply > 0
    ? `We start where this line leaves the main line. I'll show each ${sideName(L.side)} move with an arrow: play it on the board. I play ${other}.`
    : `You play ${sideName(L.side)}. I'll show each of your moves with an arrow and tell you why: play it on the board. I'll play ${other}'s replies and explain them too.`);
  renderChrome();
}

function learnStep() {
  const line = plies();
  if (ply >= line.length) { finishLearn(); return; }
  const m = line[ply];
  if (m.color === L.side) {
    waiting = 'move';
    setBoard(ply, { movable: true, hint: 2 });
    setCoach('happy', `Your move: play ${label(m)}`, m.comment);
  } else {
    // the other side's reply: play it, explain it, wait for Continue
    ply += 1;
    playMoveSound(m.san);
    waiting = 'continue';
    setBoard(ply);
    setCoach('thinking', `${sideName(m.color)} plays ${label(m)}`, m.comment);
  }
  renderChrome();
}

/** The user's move of the lesson was made (on the board or with "Play it for me"). */
function learnAdvance() {
  const m = plies()[ply];
  playMoveSound(m.san);
  ply += 1;
  waiting = null;
  setBoard(ply, { cls: 'best' });
  renderChrome();
  const mine = token;
  // a short pause so you see your move land before the reply comes
  setTimeout(() => { if (mine === token && mode === 'learn') learnStep(); }, plies()[ply] ? 650 : 350);
}

function finishLearn() {
  const hadExtras = extrasUnlocked();
  mark('openingsTutorial', { [lineIdx]: true });
  const line = L.lines[lineIdx];
  leaveMode();
  setBoard(ply, { cls: 'best' });
  const extra = L.lines.length - 1;
  let text;
  if (lineIdx === 0) {
    text = `That is the main line of the ${L.name}. Now press Practice from memory and play it without my arrows.`;
    if (extra && !hadExtras) text += ` I also unlocked ${extra} extra line${extra === 1 ? '' : 's'} above: what to do when your opponent plays something else.`;
  } else {
    text = `Now you know "${line.name}". Practice it from memory, or pick another line.`;
  }
  setCoach('surprised', 'Lesson complete!', text);
  renderLines();
  renderChrome();
}

// ================================================================ practice
// You play the moves of the lesson's side from memory; the other side's moves
// are played for you. Hint: first the piece (blue), then the move (arrow).
function startPractice() {
  stopPlay();
  leaveMode();
  mode = 'practice';
  ply = 0;
  setBoard(0);
  setCoach('thinking', `Practice: ${L.lines[lineIdx].name}`,
    `You play ${sideName(L.side)} from memory; I'll answer for ${sideName(L.side === 'w' ? 'b' : 'w')}. Stuck? Press Hint: first I show the piece, then the move.`);
  renderChrome();
  practiceStep(900);
}

/** Either wait for the user's move or play the book reply. */
function practiceStep(delay = 0) {
  const mine = token;
  const line = plies();
  if (ply >= line.length) { finishPractice(); return; }
  const m = line[ply];
  hintLevel = 0;
  if (m.color === L.side) {
    setBoard(ply, { movable: true });
    renderChrome();
    return;
  }
  renderChrome();
  setTimeout(() => {
    if (mine !== token || mode !== 'practice') return;
    ply += 1;
    playMoveSound(m.san);
    if (ply >= line.length) { setBoard(ply); finishPractice(); return; }
    setBoard(ply, { movable: true });
    setCoach('thinking', `${sideName(m.color)} plays ${m.san}`, `${m.comment} Your move.`);
    renderChrome();
  }, delay);
}

function finishPractice() {
  mark('openingsLines', { [lineIdx]: true });
  mark('openingsTutorial', { [lineIdx]: true });      // knowing it by heart counts as learned
  if (lineIdx === 0) mark('openingsLearned', true);
  const name = L.lines[lineIdx].name;
  leaveMode();
  setBoard(ply, { cls: 'best' });
  setCoach('surprised', 'Line complete!', lineIdx === 0
    ? `You played the main line of the ${L.name} from memory. ${L.lines.length > 1 ? 'Try the extra lines next.' : 'Well done!'}`
    : `You know "${name}" by heart. Well done!`);
  renderLines();
  renderChrome();
}

function practiceHint() {
  const m = plies()[ply];
  if (mode !== 'practice' || !m || m.color !== L.side || hintLevel >= 2) return;
  hintLevel += 1;
  const [from, to] = squares(m.uci);
  const piece = PIECE_NAMES[new Chess(fenAt(ply)).get(from).type];
  setBoard(ply, { movable: true, hint: hintLevel });
  if (hintLevel === 1) setCoach('thinking', `Hint: the ${piece}`, `Move the ${piece} I marked in blue on ${from}. Still not sure where? Ask again and I'll show the move.`);
  else setCoach('thinking', `Hint: ${m.san}`, `The ${piece} goes to ${to}. ${m.comment}`);
  renderChrome();
}

function onUserMove(orig, dest) {
  const expected = plies()[ply];
  const waitingForMove = (mode === 'learn' && waiting === 'move') || mode === 'practice';
  if (!waitingForMove || !expected) { if (mode === 'browse') render(); else setBoard(ply); return; }
  const played = tryMove(new Chess(fenAt(ply)), orig, dest);
  const right = played && played.from + played.to === expected.uci.slice(0, 4);
  if (mode === 'learn') {
    if (right) { learnAdvance(); return; }
    setBoard(ply, { movable: true, hint: 2 });
    setCoach('worried', played ? `${played.san} is not the move here` : 'Not that one',
      `Follow the blue arrow: the move is ${expected.san}. ${expected.comment}`);
    return;
  }
  if (right) {
    playMoveSound(played.san);
    ply += 1;
    setBoard(ply, { cls: 'best' });
    setCoach('happy', `${expected.san} — correct!`, expected.comment);
    practiceStep(1500);
    return;
  }
  setBoard(ply, { movable: true, hint: hintLevel });
  setCoach('worried', played ? `${played.san} is not in this line` : 'Not that one',
    hintLevel ? 'Look at the hint on the board and try again.' : 'Try again, or press Hint and I\'ll show you which piece to move.');
}

// ================================================================ controls
function exitMode() {
  if (mode === 'browse') return;
  const was = mode;
  leaveMode();
  render();
  toast(was === 'learn' ? 'Lesson stopped.' : 'Practice stopped.');
}

function mainAction() {
  if (mode === 'browse') { startLearn(); return; }
  if (mode !== 'learn') return;
  if (waiting === 'start' || waiting === 'continue') learnStep();
  else if (waiting === 'move') learnAdvance();
}

$('#btn-main').addEventListener('click', mainAction);
$('#btn-practice').addEventListener('click', startPractice);
$('#btn-hint').addEventListener('click', practiceHint);
$('#btn-exit').addEventListener('click', exitMode);
$('#line-choice').addEventListener('click', e => {
  const button = e.target.closest('[data-line]');
  if (button) chooseLine(Number(button.dataset.line));
});
$('#moves').addEventListener('click', e => {
  const button = e.target.closest('[data-ply]');
  if (button && mode === 'browse') goTo(Number(button.dataset.ply));
});
$('#nav-first').addEventListener('click', () => goTo(0));
$('#nav-prev').addEventListener('click', () => goTo(ply - 1));
$('#nav-next').addEventListener('click', () => goTo(ply + 1));
$('#nav-last').addEventListener('click', () => goTo(plies().length));
$('#nav-play').addEventListener('click', togglePlay);
$('#nav-flip').addEventListener('click', flip);

function flip() {
  orientation = orientation === 'white' ? 'black' : 'white';
  cg.set({ orientation });
  cg.redrawAll();
  // redraw the hint arrow (if any) for the new orientation
  const movable = (mode === 'learn' && waiting === 'move') || (mode === 'practice' && plies()[ply] && plies()[ply].color === L.side);
  setBoard(ply, { movable, hint: mode === 'learn' && waiting === 'move' ? 2 : hintLevel });
}

document.addEventListener('keydown', e => {
  if (!L || e.metaKey || e.ctrlKey || e.altKey) return;
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
  if ((e.key === ' ' || e.key === 'Enter') && e.target.tagName === 'BUTTON') return;
  const learning = mode === 'learn';
  const actions = {
    ArrowRight: () => (learning ? (waiting !== 'move' && mainAction()) : goTo(ply + 1)),
    Enter: () => { if (learning && waiting !== 'move') mainAction(); },
    ArrowLeft: () => goTo(ply - 1),
    ArrowUp: () => goTo(0), ArrowDown: () => goTo(plies().length),
    ' ': () => (learning ? (waiting !== 'move' && mainAction()) : togglePlay()),
    h: practiceHint, H: practiceHint, f: flip, F: flip,
    Escape: exitMode,
  };
  if (actions[e.key]) { e.preventDefault(); actions[e.key](); }
});

boot();

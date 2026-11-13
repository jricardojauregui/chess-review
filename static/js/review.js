// Review page. The board opens immediately; from there you can
//   - step through the game (or let it play by itself),
//   - press "Analyze game" (progress is shown in the coach card),
//   - read the summary and go through the move-by-move review,
//   - play your own moves at any point ("what if?"): the engine evaluates
//     them live and shows its best lines.
import { Chessground } from '../vendor/chessground.min.js';
import { Chess } from '../vendor/chess.js';
import {
  $, CLS, analyze, api, avatarHTML, badgeSVG, drawArrows, efforts, engineCount, enginesText, escapeHtml,
  estimateTime, fetchAvatar, formatClock, formatTimeControl, labelFromLoss, legalDests, playMoveSound,
  presetByDepth, presetById, presets, saveSettings, settings, showCoach, squareXY, toast, tryMove,
} from './common.js';
import { createEvalChart } from './evalchart.js';

const gameId = $('#app').dataset.gameId;
const params = new URLSearchParams(location.search);

let R = null;               // game (+ review once analysed) from the server
let cg = null;              // chessground instance
let chart = null;           // eval chart (review view)
let miniChart = null;       // eval chart (summary)
let ply = 0;                // 0 = start position, n = after the n-th game move
let orientation = 'white';
let view = 'pre';           // pre | analyzing | summary | review
let mode = 'normal';        // normal | best | retry | solved
let variation = null;       // { base, nodes: [{fenBefore, fen, san, uci, cls, ...}], idx }
let exploreToken = 0;
let avatars = { w: null, b: null };
let level = settings.engine;   // analysis level picked for this game (default from Settings)

const pick = list => list[Math.floor(Math.random() * list.length)];
const turnOf = fen => (fen.split(' ')[1] === 'w' ? 'white' : 'black');
const currentMove = () => (ply > 0 ? R.moves[ply - 1] : null);
const gameFen = p => (p > 0 ? R.moves[p - 1].fen_after : R.start.fen);

// =================================================================== boot
async function boot() {
  showCoach($('#loading-coach'), 'thinking');
  try {
    const depth = params.get('depth');
    const res = await api(`/api/review/${gameId}${depth ? `?depth=${depth}` : ''}`);
    R = res.data;
  } catch (e) {
    showCoach($('#loading-coach'), 'worried');
    $('#loading-title').textContent = 'Could not open this game';
    $('#loading-error').textContent = e.message;
    $('#loading-error').hidden = false;
    $('#loading-back').hidden = false;
    return;
  }
  orientation = R.hero === 'b' ? 'black' : 'white';
  $('#stage-loading').hidden = true;
  $('#stage-main').hidden = false;
  initBoard();
  loadAvatars();
  const startPly = params.get('ply');
  if (R.analysed) view = startPly !== null ? 'review' : 'summary';
  else view = 'pre';
  onGameData();
  goTo(startPly !== null ? Number(startPly) : 0, { silent: true });
}

function initBoard() {
  cg = Chessground($('#board'), {
    fen: R.start.fen,
    orientation,
    coordinates: true,
    animation: { enabled: true, duration: 200 },
    highlight: { lastMove: false, check: true },
    movable: { free: false, color: undefined, showDests: true, events: { after: onUserMove } },
    premovable: { enabled: false },
    draggable: { showGhost: true },
    drawable: { enabled: true, visible: true },
  });
  window.addEventListener('resize', () => cg.redrawAll());
  document.addEventListener('settingschange', () => cg.redrawAll());
}

async function loadAvatars() {
  if (!(R.game.url || '').includes('chess.com')) return;   // only chess.com games have profiles
  const [w, b] = await Promise.all([fetchAvatar(R.game.white.name), fetchAvatar(R.game.black.name)]);
  avatars = { w, b };
  renderPlayerBars();
  if (R.analysed) renderPlayers();
}

/** (Re)build everything that depends on R: meta, move list, charts, summary. */
function onGameData() {
  renderMeta();
  renderMoveList();
  if (chart) { chart.destroy(); chart = null; }
  if (miniChart) { miniChart.destroy(); miniChart = null; }
  const used = R.analysed ? presetByDepth(R.depth) : null;
  $('#depth-note').textContent = R.analysed ? `Stockfish · ${used ? `${used.name} · ` : ''}depth ${R.depth}` : '';
  layout();
  if (R.analysed) renderSummary();
}

/** Show / hide the parts of the side panel for the current state. */
function layout() {
  const exploring = Boolean(variation);
  const summary = view === 'summary' && !exploring;
  $('#summary').hidden = !summary;
  $('#coach-card').hidden = summary;
  $('#actions-pre').hidden = !(view === 'pre' && !exploring);
  $('#progress-box').hidden = view !== 'analyzing';
  $('#actions-review').hidden = !(view === 'review' && !exploring);
  $('#explore-box').hidden = !exploring;
  $('#chart-card').hidden = !(R.analysed && !summary);
  $('#moves-card').hidden = summary;            // keeps the summary short: no scrolling for the essentials
  $('#legend').hidden = !(view === 'review' && !exploring);
  $('#back-summary').hidden = !(R.analysed && view === 'review' && !exploring);
  if (R.analysed && !summary && !chart) chart = createEvalChart($('#eval-chart'), R, { onSelect: p => goTo(p) });
  if (summary && !miniChart) {
    miniChart = createEvalChart($('#summary-chart'), R, { compact: true, onSelect: p => { view = 'review'; goTo(p); } });
  }
  paintLevels();
}

/** Level pickers (before analysing, and "analyze again" in the summary). */
function paintLevels() {
  const p = presetById(level);
  const positions = R.moves.length + 1;
  const engines = engineCount();
  const note = `<b>${p.name}</b> · depth ${p.depth} · ${estimateTime(p, positions)} for this game with ${enginesText(engines)}` +
    (p.cost >= 4 ? `. ${engines === 1 ? 'One CPU core stays' : `${engines} CPU cores stay`} busy until it finishes.` : '');
  for (const prefix of ['#analyze', '#reanalyze']) {
    $(`${prefix}-level`).innerHTML = presets.map(x =>
      `<option value="${x.id}" ${x.id === level ? 'selected' : ''}>${x.name} · depth ${x.depth}</option>`).join('');
    $(`${prefix}-effort`).innerHTML = efforts.map(x =>
      `<option value="${x.id}" ${x.id === settings.effort ? 'selected' : ''}>${x.name} · ${x.workers} engine${x.workers === 1 ? '' : 's'}</option>`).join('');
    $(`${prefix}-note`).innerHTML = note;
    $(`${prefix}-note`).classList.toggle('warn', p.cost >= 4);
  }
  if (R.analysed) {
    const same = p.depth === R.depth;
    $('#reanalyze').disabled = same;
    $('#reanalyze').textContent = same ? `Already analyzed at ${p.name}` : `Re-analyze at ${p.name}`;
  }
}
// Effort is a saved preference (it only changes the speed), so picking it here
// also changes the default in Settings; the level is just for this game.
for (const prefix of ['#analyze', '#reanalyze']) {
  $(`${prefix}-level`).addEventListener('change', e => { level = e.target.value; paintLevels(); });
  $(`${prefix}-effort`).addEventListener('change', e => { saveSettings({ effort: e.target.value }); paintLevels(); });
}

// =============================================================== analysis
async function runAnalysis(depth) {
  view = 'analyzing';
  layout();
  $('#progress-fill').style.width = '0%';
  $('#progress-label').textContent = 'Starting the engine…';
  $('#coach-card').hidden = false;
  $('#summary').hidden = true;
  setCoach({ expression: 'thinking', title: 'Analyzing your game', text: `Stockfish is going through every move at depth ${depth} with ${enginesText(engineCount())}. You can keep looking at the board meanwhile.` });
  try {
    await analyze(gameId, depth, onProgress);
    const res = await api(`/api/review/${gameId}?depth=${depth}`);
    R = res.data;
    view = 'summary';
    variation = null;
    onGameData();
    render();
  } catch (e) {
    view = R.analysed ? 'summary' : 'pre';
    layout();
    if (view === 'pre') setCoach({ expression: 'worried', title: 'The analysis failed', text: e.message });
    else toast(e.message);
  }
}

function onProgress(p) {
  if (p.status === 'queued' || !p.total) {
    $('#progress-label').textContent = 'Waiting for the engine…';
    return;
  }
  const pct = Math.round((100 * p.done) / p.total);
  $('#progress-fill').style.width = `${pct}%`;
  $('#progress').setAttribute('aria-valuenow', pct);
  $('#progress-label').innerHTML = p.done >= p.total ? 'Putting the review together<span class="dots"></span>'
    : `Analyzing move ${p.done + 1}/${p.total}<span class="dots"></span>`;
}

$('#btn-analyze').addEventListener('click', () => runAnalysis(presetById(level).depth));
$('#reanalyze').addEventListener('click', () => runAnalysis(presetById(level).depth));

// ================================================================ summary
function renderPlayers() {
  const g = R.game, acc = R.summary.accuracy, cc = g.cc_accuracy;
  const card = (color, side) => {
    const p = g[side];
    const you = R.hero === color ? ' <span class="muted">(you)</span>' : '';
    const value = acc[color] === null ? '–' : acc[color].toFixed(1);
    const theirs = cc && cc[color] ? `<div class="cc">chess.com: ${cc[color].toFixed(1)}</div>` : '';
    return `<div class="card player-card ${side}">
      ${avatarHTML(p.name, avatars[color])}
      <div class="name">${escapeHtml(p.name)}${you}</div>
      <div class="muted" style="font-size:13px">${p.rating ? p.rating : '&nbsp;'}</div>
      <div class="acc-box"><div class="acc">${value}</div><div class="acc-label">Accuracy</div>${theirs}</div>
    </div>`;
  };
  $('#summary-players').innerHTML = card('w', 'white') + card('b', 'black');
  const result = (g.result || '*').replace('1/2-1/2', '½-½');
  $('#summary-result').innerHTML = `<b>${result}</b>${escapeHtml(formatTimeControl(g.time_control))}${g.date ? ` · ${escapeHtml(g.date)}` : ''}`;
}

function renderSummary() {
  const s = R.summary;
  showCoach($('#summary-coach'), s.comment.expression);
  $('#summary-comment').textContent = s.comment.text;
  renderPlayers();
  const rows = R.labels
    .filter(label => label !== 'forced' || s.counts.w.forced + s.counts.b.forced > 0)
    .map(label => {
      const w = s.counts.w[label], b = s.counts.b[label];
      return `<tr><td class="n ${w ? '' : 'zero'}">${w}</td>
        <td class="label">${badgeSVG(label, 20)}${CLS[label].label}</td>
        <td class="n ${b ? '' : 'zero'}">${b}</td></tr>`;
    }).join('');
  $('#summary-counts').innerHTML = `<thead><tr><th>White</th><th></th><th>Black</th></tr></thead><tbody>${rows}</tbody>`;
  const phaseNames = { opening: 'Opening', middlegame: 'Middlegame', endgame: 'Endgame' };
  const cell = p => (p
    ? `${badgeSVG(p.quality, 20)} <span class="muted" style="font-weight:500;font-size:13px">${p.accuracy.toFixed(0)}%</span>`
    : '<span class="muted">–</span>');
  $('#summary-phases').innerHTML = `<tbody>${Object.entries(phaseNames).map(([key, name]) =>
    `<tr><td class="n">${cell(s.phases[key].w)}</td><td class="label">${name}</td><td class="n">${cell(s.phases[key].b)}</td></tr>`
  ).join('')}</tbody>`;
  const used = presetByDepth(R.depth);
  $('#reanalyze-title').textContent = `Analyzed at ${used ? used.name : 'depth ' + R.depth} · analyze again at another level`;
}

$('#start-review').addEventListener('click', () => { view = 'review'; goTo(0, { silent: true }); });
$('#back-summary').addEventListener('click', () => { stopPlay(); view = 'summary'; variation = null; render(); });

// ============================================================== rendering
function renderMeta() {
  const g = R.game;
  const opening = g.opening_book ? `${g.opening_book.eco} · ${g.opening_book.name}` : (g.opening || 'Game');
  // Opening and the link to the original game share one line
  let html = `<span class="opening" title="${escapeHtml(opening)}">${escapeHtml(opening)}</span>`;
  if (g.url && /^https?:\/\//.test(g.url)) html += `<a href="${escapeHtml(g.url)}" target="_blank" rel="noopener" title="Open this game on chess.com">chess.com ↗</a>`;
  $('#game-meta').innerHTML = html;
}

function renderMoveList() {
  let html = '';
  R.moves.forEach((m, i) => {
    if (m.color === 'w' || i === 0) html += `<div class="no">${m.move_number}.</div>`;
    if (i === 0 && m.color === 'b') html += '<div class="mv" style="cursor:default">…</div>';
    const badge = m.cls ? badgeSVG(m.cls, 18) : '';
    html += `<button class="mv" data-ply="${m.ply}" ${m.cls ? `title="${CLS[m.cls].label}"` : ''}>${badge}<span>${escapeHtml(m.san)}</span></button>`;
  });
  $('#moves').innerHTML = html;
}
$('#moves').addEventListener('click', e => {
  const button = e.target.closest('[data-ply]');
  if (button) goTo(Number(button.dataset.ply));
});

// Captured pieces are worked out from the position itself (what is missing
// from each army), so they are also right while exploring a variation.
const ARMY = { p: 8, n: 2, b: 2, r: 2, q: 1 };
const PIECE_VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9 };

/** { lost: {w: {p,n,b,r,q}, b: {...}}, points: {w, b} } for a FEN. */
function material(fen) {
  const count = { w: { p: 0, n: 0, b: 0, r: 0, q: 0 }, b: { p: 0, n: 0, b: 0, r: 0, q: 0 } };
  for (const ch of fen.split(' ')[0]) {
    const type = ch.toLowerCase();
    if (type in ARMY) count[ch === type ? 'b' : 'w'][type] += 1;
  }
  const lost = { w: {}, b: {} }, points = { w: 0, b: 0 };
  for (const color of ['w', 'b']) {
    let promoted = 0;
    for (const type of Object.keys(ARMY)) {
      const missing = ARMY[type] - count[color][type];
      if (missing < 0) promoted -= missing;          // an extra piece came from a pawn
      lost[color][type] = Math.max(0, missing);
      points[color] += count[color][type] * PIECE_VALUE[type];
    }
    lost[color].p = Math.max(0, lost[color].p - promoted);   // promoted pawns were not captured
  }
  return { lost, points };
}

/** Pieces `color` has captured (grouped by type) and its material lead. */
function capturedHTML(color, mat) {
  const other = color === 'w' ? 'b' : 'w';
  let html = '';
  for (const type of Object.keys(ARMY)) {
    const n = mat.lost[other][type];
    if (!n) continue;
    // Always the same line drawing (not the board's piece set): the white piece's
    // artwork, which CSS turns into a dark piece with a light outline for .cap.b
    const img = `<img class="cap ${other}" src="/static/img/pieces/cburnett/w${type.toUpperCase()}.svg" alt="">`;
    html += `<span class="cap-group" title="${n} × ${{ p: 'pawn', n: 'knight', b: 'bishop', r: 'rook', q: 'queen' }[type]}">${img.repeat(n)}</span>`;
  }
  const lead = mat.points[color] - mat.points[other];
  if (lead > 0) html += `<span class="cap-lead">+${lead}</span>`;
  return html;
}

function renderPlayerBars() {
  if (!R) return;
  const g = R.game;
  const clockAt = color => {
    for (let i = ply - 1; i >= 0; i--) if (R.moves[i].color === color) return R.moves[i].clock;
    return null;
  };
  const exploring = variation && variation.idx >= 0;
  const mat = material(exploring ? variation.nodes[variation.idx].fen : gameFen(ply));
  const bar = color => {
    const p = color === 'w' ? g.white : g.black;
    return `${avatarHTML(p.name, avatars[color])}
      <div class="who">
        <div class="who-line"><span class="name">${escapeHtml(p.name)}</span><span class="rating">${p.rating ? `(${p.rating})` : ''}</span></div>
        <div class="captured" aria-label="Captured pieces">${capturedHTML(color, mat)}</div>
      </div>
      <span class="clock">${variation ? '' : formatClock(clockAt(color))}</span>`;
  };
  const top = orientation === 'white' ? 'b' : 'w';
  $('#player-top').innerHTML = bar(top);
  $('#player-bottom').innerHTML = bar(top === 'w' ? 'b' : 'w');
}

/** Put a position on the board. Pieces are movable unless `locked`. */
function setBoard({ fen, lastMove, cls, arrows = [], marks = [], locked = false }) {
  const game = new Chess(fen);
  const custom = new Map();
  if (lastMove) for (const sq of lastMove) custom.set(sq, `hl-${cls || 'plain'}`);
  // coach squares (same colours as the arrows); never repaint the move's own squares
  for (const mark of marks) if (!custom.has(mark.square)) custom.set(mark.square, `mark-${mark.kind}`);
  const canMove = !locked && !game.isGameOver();
  cg.set({
    fen,
    orientation,
    turnColor: turnOf(fen),
    lastMove: lastMove || undefined,
    check: game.inCheck(),
    highlight: { lastMove: false, check: true, custom },
    movable: { color: canMove ? turnOf(fen) : undefined, dests: canMove ? legalDests(game) : new Map() },
    drawable: { autoShapes: [] },
  });
  cg.setShapes([]);
  drawArrows($('#arrows'), arrows, orientation);
  const badge = $('#move-badge');
  if (lastMove && cls && cls !== 'plain') {
    const { x, y } = squareXY(lastMove[1], orientation);
    badge.style.left = `${(x + 1) * 12.5}%`;
    badge.style.top = `${y * 12.5}%`;
    badge.innerHTML = badgeSVG(cls, 32);
    badge.hidden = false;
    badge.style.animation = 'none'; void badge.offsetWidth; badge.style.animation = '';
  } else {
    badge.hidden = true;
  }
}

function setEvalBar(winWhite, ev) {
  const bar = $('#evalbar'), num = $('#evalbar-num');
  bar.classList.toggle('flipped', orientation === 'black');
  if (winWhite === null) {              // no evaluation available (game not analysed)
    $('#evalbar-fill').style.height = '50%';
    num.textContent = '';
    return;
  }
  $('#evalbar-fill').style.height = `${Math.max(3, Math.min(97, winWhite))}%`;
  let text;
  if (ev.mate !== null && ev.mate !== undefined) text = ev.mate === 0 ? '#' : `M${Math.abs(ev.mate)}`;
  else text = Math.abs(ev.cp / 100).toFixed(1);
  num.textContent = text;
  const whiteBetter = winWhite >= 50;
  num.classList.toggle('white-side', whiteBetter);
  num.classList.toggle('black-side', !whiteBetter);
}

/** "Explain why": the reason behind the classification, opened on demand. */
function setWhy(explain, open = false) {
  const button = $('#btn-why'), box = $('#bubble-why');
  const has = Boolean(explain && explain.text.length);
  const shown = has && open;
  button.disabled = !has;
  button.classList.toggle('on', shown);
  button.setAttribute('aria-pressed', String(shown));
  // the explanation takes the place of the coach's comment instead of growing the bubble
  box.hidden = !shown;
  $('#bubble-text').hidden = shown;
  $('#bubble-line').hidden = shown;
  box.innerHTML = has ? explain.text.map(t => `<p>${escapeHtml(t)}</p>`).join('')
    + explain.lines.map(l => `<p class="why-line">${escapeHtml(l.label)}: <b>${escapeHtml(l.moves)}</b></p>`).join('') : '';
}
function toggleWhy() {
  const m = currentMove();
  if ($('#btn-why').disabled || !m || !m.coach || mode !== 'normal' || variation) return;
  setWhy(m.coach.explain, $('#bubble-why').hidden);
}

function setCoach({ expression, cls, title, evalText, text, line, explain }) {
  setWhy(explain);
  showCoach($('#coach-avatar'), expression);     // the owl moves into the new pose
  $('#bubble-icon').innerHTML = cls ? badgeSVG(cls, 24) : '';
  $('#bubble-title').textContent = title || '';
  const chip = $('#bubble-eval');
  chip.hidden = !evalText;
  chip.textContent = evalText || '';
  chip.classList.toggle('black', Boolean(evalText) && evalText.startsWith('-'));
  $('#bubble-text').textContent = text || '';
  $('#bubble-line').innerHTML = line || '';
  const bubble = $('#bubble');
  bubble.classList.remove('pop'); void bubble.offsetWidth; bubble.classList.add('pop');
}

const uciSquares = uci => [uci.slice(0, 2), uci.slice(2, 4)];
const bestLineHTML = m => (m.best ? `Best: <b>${escapeHtml(m.best.san)}</b> <span>(${m.best.eval.text})</span>` : '');

/**
 * Coach arrows and squares for a reviewed move, with chess.com's colour meanings:
 *   orange = the main idea of the move (what it attacks, a check)
 *   red    = a threat / problem: the reply that punishes a mistake
 *   green  = the stronger move that was available
 *   blue   = the opponent's concrete response (a capture)
 */
function reviewArrows(m) {
  if (!m || !R.analysed || view !== 'review') return { arrows: [], marks: [] };
  const arrows = [], marks = [];
  for (const idea of m.ideas || []) arrows.push({ orig: idea.orig, dest: idea.dest, kind: 'idea' });
  if (m.punish) {
    arrows.push({ orig: m.punish.slice(0, 2), dest: m.punish.slice(2, 4), kind: 'punish' });
    marks.push({ square: m.punish.slice(2, 4), kind: 'danger' });
  } else if (m.reply) {
    arrows.push({ orig: m.reply.slice(0, 2), dest: m.reply.slice(2, 4), kind: 'reply' });
  }
  if (m.best && !m.is_best && m.cls !== 'book') {
    arrows.push({ orig: m.best.uci.slice(0, 2), dest: m.best.uci.slice(2, 4), kind: 'best' });
  }
  return { arrows, marks };
}

/** Render the current game position (not exploring). */
function render() {
  mode = 'normal';
  variation = null;
  layout();
  const m = currentMove();
  const coach = reviewArrows(m);
  setBoard({ fen: gameFen(ply), lastMove: m ? uciSquares(m.uci) : null, cls: m ? m.cls : null, ...coach });
  if (R.analysed) setEvalBar(m ? m.win_white : R.start.win_white, m ? m.eval : R.start.eval);
  else setEvalBar(null);

  if (view === 'pre') {
    setCoach({
      expression: 'happy', title: 'Ready when you are',
      text: 'Step through the game or try your own moves on the board. Press Analyze game and I\'ll review every move.',
    });
  } else if (view === 'review') {
    if (m) {
      setCoach({
        expression: m.coach.expression, cls: m.cls, title: m.coach.title, evalText: m.eval.text,
        text: m.coach.text, line: m.is_best || m.cls === 'book' ? '' : bestLineHTML(m),
        explain: m.coach.explain,
      });
    } else {
      setCoach({ expression: 'happy', title: "Let's review!", text: R.coach_lines.intro[0] });
    }
  }

  const canImprove = Boolean(R.analysed && m && m.best && !m.is_best && m.cls !== 'book' && m.cls !== 'forced');
  $('#btn-best').disabled = !canImprove;
  $('#btn-best').textContent = 'Show best move';
  $('#btn-retry').disabled = !canImprove;
  $('#btn-retry').textContent = 'Retry';
  const atEnd = ply >= R.moves.length;
  $('#btn-next').disabled = $('#nav-next').disabled = $('#nav-last').disabled = atEnd;
  $('#nav-prev').disabled = $('#nav-first').disabled = ply <= 0;

  for (const node of document.querySelectorAll('#moves .mv.current')) node.classList.remove('current');
  const active = $(`#moves .mv[data-ply="${ply}"]`);
  if (active) {
    active.classList.add('current');
    // Keep the current move in view inside the move list (never scroll the page)
    const box = $('#moves-card');
    const r = active.getBoundingClientRect(), b = box.getBoundingClientRect();
    if (r.top < b.top) box.scrollTop -= b.top - r.top + 6;
    else if (r.bottom > b.bottom) box.scrollTop += r.bottom - b.bottom + 6;
  } else $('#moves-card').scrollTop = 0;
  if (chart) chart.setCursor(ply);
  renderPlayerBars();
}

function goTo(target, { silent = false, auto = false } = {}) {
  if (!auto) stopPlay();                 // any manual navigation pauses the autoplay
  const next = Math.max(0, Math.min(R.moves.length, target));
  if (!silent && !variation) {
    if (next === ply + 1) playMoveSound(R.moves[next - 1].san);
    else if (next === ply - 1) playMoveSound(R.moves[ply - 1].san);
  }
  ply = next;
  render();
}

// ============================================================== autoplay
// The play button steps through the game on its own; pressing it again (or
// doing anything else on the board) pauses it.
const PLAY_INTERVAL_MS = 1100;
let playTimer = null;

function paintPlay() {
  const button = $('#nav-play'), playing = playTimer !== null;
  button.classList.toggle('playing', playing);
  button.setAttribute('aria-pressed', String(playing));
  button.title = playing ? 'Pause (Space)' : 'Play the game (Space)';
  button.setAttribute('aria-label', playing ? 'Pause' : 'Play the game');
}

function stopPlay() {
  if (playTimer === null) return;
  clearInterval(playTimer);
  playTimer = null;
  paintPlay();
}

function togglePlay() {
  if (playTimer !== null) { stopPlay(); return; }
  if (variation || mode !== 'normal') render();                     // back to the game first
  if (ply >= R.moves.length) goTo(0, { silent: true, auto: true });  // at the end: play again
  playTimer = setInterval(() => {
    if (variation || mode !== 'normal' || ply >= R.moves.length) { stopPlay(); return; }
    goTo(ply + 1, { auto: true });
    if (ply >= R.moves.length) stopPlay();
  }, PLAY_INTERVAL_MS);
  paintPlay();
}

// ====================================================== show best / retry
function showBest() {
  stopPlay();
  const m = currentMove();
  if (mode === 'best') { render(); return; }
  mode = 'best';
  const game = new Chess(m.fen_before);
  const [from, to] = uciSquares(m.best.uci);
  try { game.move({ from, to, promotion: m.best.uci[4] || undefined }); } catch (e) { return; }
  playMoveSound(m.best.san);
  setBoard({ fen: game.fen(), lastMove: [from, to], cls: 'best', locked: true });
  setCoach({
    expression: 'happy', cls: 'best', title: `${m.best.san} is best`, evalText: m.best.eval.text,
    text: pick(R.coach_lines.show_best).replace('{best}', m.best.san),
    line: `Line: <b>${escapeHtml(m.best.pv_san.join(' '))}</b>`,
  });
  $('#btn-best').textContent = 'Back to game';
  $('#btn-retry').textContent = 'Retry';
}

function startRetry(message) {
  stopPlay();
  const m = currentMove();
  mode = 'retry';
  const prev = ply >= 2 ? R.moves[ply - 2] : null;
  setBoard({ fen: m.fen_before, lastMove: prev ? uciSquares(prev.uci) : null });
  setCoach({
    expression: 'thinking', title: `Find a better move than ${m.san}`,
    text: message || pick(R.coach_lines.retry_start),
  });
  $('#btn-retry').textContent = 'Cancel';
  $('#btn-best').textContent = 'Show best move';
}

function onRetryMove(orig, dest) {
  const m = currentMove();
  const game = new Chess(m.fen_before);
  const played = tryMove(game, orig, dest);
  if (!played) { startRetry(); return; }
  playMoveSound(played.san);
  const uci = played.from + played.to + (played.promotion || '');
  // Accept the engine's best move, or anything within a whisker of it
  const good = m.good_moves.some(g => g === uci || (g.length === 4 && g === uci.slice(0, 4)));
  if (good) {
    mode = 'solved';
    setBoard({ fen: game.fen(), lastMove: [played.from, played.to], cls: 'best', locked: true });
    const isTop = uci.slice(0, 4) === m.best.uci.slice(0, 4);
    setCoach({
      expression: 'surprised', cls: 'best', title: `${played.san} — you found it!`, evalText: m.best.eval.text,
      text: isTop ? pick(R.coach_lines.retry_success).replace('{best}', played.san)
                  : `Yes! ${played.san} is just as good as my ${m.best.san}.`,
      line: isTop ? `Line: <b>${escapeHtml(m.best.pv_san.join(' '))}</b>` : '',
    });
    $('#btn-retry').textContent = 'Retry';
    return;
  }
  const same = uci.slice(0, 4) === m.uci.slice(0, 4);
  setBoard({ fen: game.fen(), lastMove: [played.from, played.to], cls: same ? m.cls : 'mistake', locked: true });
  setCoach({
    expression: 'worried', cls: same ? m.cls : 'mistake', title: `${played.san}?`,
    text: same ? "That's the move from the game. Try something different!" : pick(R.coach_lines.retry_fail),
  });
  setTimeout(() => { if (mode === 'retry' && currentMove() === m) startRetry('Have another look. What else is there?'); }, 900);
}

// ============================================================ exploration
// Playing a move that is not the game move starts a variation. Each position
// is sent to the engine (/api/explore), which returns its best lines; from
// those we grade the move you tried and update the eval bar.
const evalCache = new Map();
function fetchEval(fen) {
  if (!evalCache.has(fen)) {
    const request = api('/api/explore', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fen }),
    }).then(r => r.data);
    request.catch(() => evalCache.delete(fen));
    evalCache.set(fen, request);
  }
  return evalCache.get(fen);
}

function onUserMove(orig, dest) {
  stopPlay();
  if (mode === 'retry') { onRetryMove(orig, dest); return; }
  const fen = variation ? variation.nodes[variation.idx].fen : gameFen(ply);
  const game = new Chess(fen);
  const played = tryMove(game, orig, dest);
  if (!played) { if (variation) renderExplore(); else render(); return; }
  playMoveSound(played.san);
  const uci = played.from + played.to + (played.promotion || '');
  // Replaying the move from the game just steps forward
  if (!variation && ply < R.moves.length && R.moves[ply].uci === uci) { goTo(ply + 1, { silent: true }); return; }
  if (!variation) variation = { base: ply, nodes: [], idx: -1 };
  variation.nodes = variation.nodes.slice(0, variation.idx + 1);
  variation.nodes.push({ fenBefore: fen, fen: game.fen(), san: played.san, uci, from: played.from, to: played.to });
  variation.idx = variation.nodes.length - 1;
  mode = 'normal';
  renderExplore();
}

/** Play an engine line's first move as if the user had made it. */
function playUci(uci) {
  onUserMove(uci.slice(0, 2), uci.slice(2, 4));
}

function renderVariation() {
  let html = '';
  variation.nodes.forEach((node, i) => {
    const [, turn, , , , fullmove] = node.fenBefore.split(' ');
    if (turn === 'w') html += `<span class="no">${fullmove}.</span>`;
    else if (i === 0) html += `<span class="no">${fullmove}…</span>`;
    html += `<button class="mv ${i === variation.idx ? 'current' : ''}" data-node="${i}">${node.cls ? badgeSVG(node.cls, 16) : ''}<span>${escapeHtml(node.san)}</span></button>`;
  });
  $('#variation').innerHTML = html;
}
$('#variation').addEventListener('click', e => {
  const button = e.target.closest('[data-node]');
  if (button) { variation.idx = Number(button.dataset.node); renderExplore(); }
});

function exploreMessage(node, before) {
  const best = before.lines[0] ? before.lines[0].san : null;
  let text;
  if (node.san.includes('#')) text = 'Checkmate! That would have ended the game.';
  else if (node.cls === 'best') text = "That's the engine's first choice in this position.";
  else if (node.cls === 'excellent' || node.cls === 'good') text = `A fine alternative. The engine's first choice was ${best}.`;
  else if (node.cls === 'inaccuracy') text = `Playable, but ${best} was more accurate.`;
  else text = `This doesn't work as well. ${best} was much stronger.`;
  // First move of the variation: compare it with what happened in the game
  const played = R.analysed && variation.idx === 0 ? R.moves[variation.base] : null;
  if (played && played.win_after !== undefined) {
    const diff = node.winAfter - played.win_after;
    if (diff >= 5) text += ` It improves on ${played.san} from the game.`;
    else if (diff <= -5) text += ` In the game, ${played.san} was actually better.`;
    else text += ` It is about as good as ${played.san} from the game.`;
  }
  return text;
}

function paintExplore(node) {
  const after = node.after;
  const arrows = after.lines[0] ? [{ orig: after.lines[0].uci.slice(0, 2), dest: after.lines[0].uci.slice(2, 4), kind: 'best' }] : [];
  setBoard({ fen: node.fen, lastMove: [node.from, node.to], cls: node.cls, arrows });
  setEvalBar(after.win_white, after.eval);
  setCoach({
    expression: { best: 'happy', excellent: 'happy', good: 'happy', inaccuracy: 'thinking' }[node.cls] || 'worried',
    cls: node.cls, title: `${node.san} is ${CLS[node.cls].article}`, evalText: after.eval.text, text: node.message,
  });
  renderVariation();
  const side = after.turn === 'w' ? 'White' : 'Black';
  $('#lines-title').textContent = after.lines.length ? `Best lines · ${side} to move` : 'Game over';
  $('#lines').innerHTML = after.lines.map((line, i) => {
    const [first, ...rest] = line.pv_san;
    return `<button class="line" data-uci="${line.uci}" title="Play ${escapeHtml(first)}">
      <span class="eval-chip ${line.eval.text.startsWith('-') ? 'black' : ''}">${line.eval.text}</span>
      <span class="pv"><b>${escapeHtml(first)}</b> ${escapeHtml(rest.join(' '))}</span></button>`;
  }).join('');
}

function renderExplore() {
  const node = variation.nodes[variation.idx];
  layout();
  renderPlayerBars();
  $('#btn-undo').disabled = false;
  for (const el of document.querySelectorAll('#moves .mv.current')) el.classList.remove('current');
  if (node.after) { paintExplore(node); return; }
  setBoard({ fen: node.fen, lastMove: [node.from, node.to], cls: 'plain' });
  renderVariation();
  setCoach({ expression: 'thinking', title: `What if ${node.san}?`, text: 'Let me calculate…' });
  $('#lines-title').textContent = 'Best lines';
  $('#lines').innerHTML = '<div class="muted">Calculating<span class="dots"></span></div>';
  const token = ++exploreToken;
  Promise.all([fetchEval(node.fenBefore), fetchEval(node.fen)]).then(([before, after]) => {
    // Grade the move: win% of the best move before vs. what is left after it
    const winBest = before.lines[0] ? before.lines[0].win : 50;
    let winAfter = 50;
    if (after.terminal === 'checkmate') winAfter = 100;
    else if (after.lines[0]) winAfter = 100 - after.lines[0].win;
    const loss = Math.max(0, winBest - winAfter);
    // The review (often a different depth) may already have named this move as
    // best; when the live engine agrees it loses nothing, keep calling it best.
    const reviewed = R.analysed && variation && node === variation.nodes[0] ? R.moves[variation.base] : null;
    const reviewBest = Boolean(reviewed && reviewed.best && reviewed.best.uci === node.uci && loss < window.APP.thresholds.excellent);
    const isBest = after.terminal === 'checkmate' || reviewBest || Boolean(before.lines[0] && before.lines[0].uci === node.uci);
    node.after = after;
    node.winAfter = winAfter;
    node.cls = labelFromLoss(isBest ? 0 : loss, isBest);
    if (!variation || variation.nodes[variation.idx] !== node) return;   // the user moved on
    node.message = exploreMessage(node, before);
    if (token === exploreToken) paintExplore(node);
  }).catch(e => {
    if (token !== exploreToken) return;
    setCoach({ expression: 'worried', title: 'No engine answer', text: e.message });
    $('#lines').innerHTML = '';
  });
}

function undoExplore() {
  if (!variation) return;
  playMoveSound(variation.nodes[variation.idx].san);
  variation.idx -= 1;
  if (variation.idx < 0) render(); else renderExplore();
}

$('#lines').addEventListener('click', e => {
  const button = e.target.closest('[data-uci]');
  if (button) playUci(button.dataset.uci);
});
$('#btn-undo').addEventListener('click', undoExplore);
$('#btn-exit').addEventListener('click', () => { stopPlay(); render(); });

// =============================================================== controls
$('#btn-why').addEventListener('click', toggleWhy);
$('#btn-best').addEventListener('click', showBest);
$('#btn-retry').addEventListener('click', () => (mode === 'retry' ? render() : startRetry()));
$('#btn-next').addEventListener('click', () => goTo(ply + 1));
$('#nav-first').addEventListener('click', () => goTo(0));
$('#nav-prev').addEventListener('click', () => (variation ? undoExplore() : goTo(ply - 1)));
$('#nav-next').addEventListener('click', () => stepForward());
$('#nav-play').addEventListener('click', togglePlay);
$('#nav-last').addEventListener('click', () => goTo(R.moves.length));
$('#nav-flip').addEventListener('click', flip);

function stepForward() {
  stopPlay();
  if (variation) {
    if (variation.idx < variation.nodes.length - 1) {
      variation.idx += 1;
      playMoveSound(variation.nodes[variation.idx].san);
      renderExplore();
    }
    return;
  }
  goTo(ply + 1);
}

function flip() {
  orientation = orientation === 'white' ? 'black' : 'white';
  if (variation) renderExplore();
  else if (mode === 'retry') { render(); startRetry(); }
  else render();
}

document.addEventListener('keydown', e => {
  if (!R || $('#stage-main').hidden || e.metaKey || e.ctrlKey || e.altKey) return;
  if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
  if (e.key === ' ' && e.target.tagName === 'BUTTON') return;      // Space presses the focused button
  const actions = {
    ' ': togglePlay,
    ArrowRight: stepForward, ArrowLeft: () => (variation ? undoExplore() : goTo(ply - 1)),
    ArrowUp: () => goTo(0), ArrowDown: () => goTo(R.moves.length),
    Home: () => goTo(0), End: () => goTo(R.moves.length), f: flip, F: flip,
    w: toggleWhy, W: toggleWhy,
    Escape: () => { stopPlay(); if (variation) render(); },
  };
  if (actions[e.key]) { e.preventDefault(); actions[e.key](); }
});

boot();

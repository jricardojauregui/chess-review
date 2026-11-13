// Shared helpers: classification metadata, SVG icons, the coach avatar, API calls.

// ---------------------------------------------------------------- classes
// Colours are mirrored in style.css (--c-<name>).
export const CLS = {
  brilliant:  { label: 'Brilliant',  color: '#1fb5ad', glyph: '!!', article: 'brilliant' },
  great:      { label: 'Great',      color: '#4a86d8', glyph: '!', article: 'a great move' },
  best:       { label: 'Best',       color: '#58a942', glyph: 'star', article: 'best' },
  excellent:  { label: 'Excellent',  color: '#86c463', glyph: 'thumb', article: 'excellent' },
  good:       { label: 'Good',       color: '#7a9f85', glyph: 'check', article: 'good' },
  book:       { label: 'Book',       color: '#b99466', glyph: 'book', article: 'a book move' },
  inaccuracy: { label: 'Inaccuracy', color: '#e3b62b', glyph: '?!', article: 'an inaccuracy' },
  mistake:    { label: 'Mistake',    color: '#e88130', glyph: '?', article: 'a mistake' },
  miss:       { label: 'Miss',       color: '#ea6f7a', glyph: 'cross', article: 'a miss' },
  blunder:    { label: 'Blunder',    color: '#d63d38', glyph: '??', article: 'a blunder' },
  forced:     { label: 'Forced',     color: '#868d99', glyph: 'arrow', article: 'forced' },
};
// Classifications that get a dot on the eval chart
export const NOTABLE = new Set(['brilliant', 'great', 'miss', 'mistake', 'blunder']);

const GLYPH_PATHS = {
  star: '<path fill="#fff" d="M12 4.8l2.1 4.5 4.9.6-3.6 3.4.9 4.9L12 15.9l-4.3 2.3.9-4.9L5 9.9l4.9-.6z"/>',
  thumb: '<path fill="#fff" d="M6.5 11h2.3v7H6.5zM10 11.3l2.7-5c1 0 1.7.8 1.6 1.8l-.4 2.2h3.2c.9 0 1.5.8 1.3 1.7l-1.1 4.9c-.1.6-.7 1.1-1.4 1.1H10z"/>',
  check: '<path fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" d="M7 12.6l3.3 3.3L17 9"/>',
  book: '<path fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round" d="M5.5 7.6c2.2-1 4.3-1 6.5.3 2.2-1.3 4.3-1.3 6.5-.3v9c-2.2-1-4.3-1-6.5.3-2.2-1.3-4.3-1.3-6.5-.3zM12 7.9v9"/>',
  cross: '<path fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" d="M8 8l8 8M16 8l-8 8"/>',
  arrow: '<path fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" d="M6.5 12h10M13 8.2l3.8 3.8-3.8 3.8"/>',
};

/** Circular classification badge as an SVG string. */
export function badgeSVG(cls, size = 22) {
  const meta = CLS[cls] || CLS.good;
  const g = meta.glyph;
  const inner = GLYPH_PATHS[g] ||
    `<text x="12" y="16.6" text-anchor="middle" font-family="Arial Black, Arial, sans-serif" font-weight="900" font-size="${g.length > 1 ? 11.5 : 14}" fill="#fff">${g}</text>`;
  return `<svg class="badge" width="${size}" height="${size}" viewBox="0 0 24 24" role="img" aria-label="${meta.label}">` +
    `<circle cx="12" cy="12" r="11" fill="${meta.color}" stroke="rgba(0,0,0,.35)" stroke-width="1"/>${inner}</svg>`;
}

// ------------------------------------------------------------------ coach
// "Ollie", an original owl coach. It is ONE drawing: the expression is a
// data-attribute and coach.css moves the parts (pupils, lids, brows, beak,
// wings) between poses, so changing mood animates instead of swapping images.
let coachCount = 0;

/** The coach as an SVG string. expression: happy | surprised | thinking | worried */
export function coachSVG(expression = 'happy') {
  const id = `owl${++coachCount}`;
  return `<svg class="coach-svg" viewBox="0 0 120 124" data-expression="${expression}" role="img" aria-label="Coach Ollie">
    <defs>
      <clipPath id="${id}l"><circle cx="42" cy="50" r="16"/></clipPath>
      <clipPath id="${id}r"><circle cx="78" cy="50" r="16"/></clipPath>
    </defs>
    <g class="owl">
      <path class="owl-feet" d="M46 112l-6 6M50 112v7M74 112l6 6M70 112v7" stroke="#f5a524" stroke-width="3.5" stroke-linecap="round" fill="none"/>
      <path class="owl-wing owl-wing-l" d="M18 70c-8 8-9 22-3 32 6-5 10-14 9-24z" fill="#5a49b8"/>
      <path class="owl-wing owl-wing-r" d="M102 70c8 8 9 22 3 32-6-5-10-14-9-24z" fill="#5a49b8"/>
      <g class="owl-body">
        <ellipse cx="60" cy="68" rx="42" ry="46" fill="#7462dc"/>
        <ellipse cx="60" cy="86" rx="25" ry="24" fill="#efeaff"/>
        <path d="M50 82l4 4 4-4M62 82l4 4 4-4M56 93l4 4 4-4" fill="none" stroke="#b9aef0" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      </g>
      <g class="owl-head">
        <path d="M26 32l4-20 16 12zM94 32l-4-20-16 12z" fill="#5a49b8"/>
        <g class="owl-eye" clip-path="url(#${id}l)">
          <circle cx="42" cy="50" r="16" fill="#fff"/>
          <g class="owl-pupil"><circle cx="42" cy="50" r="6.5" fill="#1b1d22"/><circle cx="44.2" cy="47.6" r="2" fill="#fff"/></g>
          <circle class="owl-lid-low" cx="42" cy="50" r="16.5" fill="#8a7ae6"/>
          <g class="owl-blink"><circle class="owl-lid-up" cx="42" cy="50" r="16.5" fill="#6a58d0"/></g>
        </g>
        <g class="owl-eye" clip-path="url(#${id}r)">
          <circle cx="78" cy="50" r="16" fill="#fff"/>
          <g class="owl-pupil"><circle cx="78" cy="50" r="6.5" fill="#1b1d22"/><circle cx="80.2" cy="47.6" r="2" fill="#fff"/></g>
          <circle class="owl-lid-low" cx="78" cy="50" r="16.5" fill="#8a7ae6"/>
          <g class="owl-blink"><circle class="owl-lid-up" cx="78" cy="50" r="16.5" fill="#6a58d0"/></g>
        </g>
        <path class="owl-brow owl-brow-l" d="M31 36q10-6 20-2" fill="none" stroke="#2c2350" stroke-width="3.5" stroke-linecap="round"/>
        <path class="owl-brow owl-brow-r" d="M89 36q-10-6-20-2" fill="none" stroke="#2c2350" stroke-width="3.5" stroke-linecap="round"/>
        <ellipse class="owl-mouth" cx="60" cy="68" rx="4.5" ry="4" fill="#8a4b12"/>
        <path class="owl-beak" d="M54 60h12l-6 9z" fill="#f5a524"/>
        <g class="owl-blush"><ellipse cx="29" cy="64" rx="5" ry="3" fill="#ff8fa3"/><ellipse cx="91" cy="64" rx="5" ry="3" fill="#ff8fa3"/></g>
      </g>
      <path class="owl-x owl-sparkle" d="M102 20l3 7 7 3-7 3-3 7-3-7-7-3 7-3z" fill="#ffd866"/>
      <g class="owl-x owl-think"><circle cx="101" cy="30" r="2.5"/><circle cx="107" cy="21" r="3.5"/><circle cx="114" cy="10" r="4.5"/></g>
      <path class="owl-x owl-sweat" d="M100 32c3 5 5 7 5 10a5 5 0 01-10 0c0-3 2-5 5-10z" fill="#7cc7ff"/>
    </g>
  </svg>`;
}

/**
 * Show the coach in `container` with an expression. If the owl is already
 * there it is NOT redrawn: its parts glide to the new pose and it reacts
 * (hop, jump, tilt, shiver) to the change.
 */
export function showCoach(container, expression = 'happy') {
  if (!container) return;
  let svg = container.querySelector('svg.coach-svg');
  if (!svg) {
    container.innerHTML = coachSVG(expression);
    return;
  }
  svg.dataset.expression = expression;
  svg.classList.remove('react');
  void svg.getBoundingClientRect();        // restart the reaction animation
  svg.classList.add('react');
}

// -------------------------------------------------------------------- API
/** fetch JSON; throws Error(message) with .status on HTTP errors. */
export async function api(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (e) {
    throw new Error('Could not reach the local server. Is app.py still running?');
  }
  let data = null;
  try { data = await response.json(); } catch (e) { /* no body */ }
  if (!response.ok) {
    const err = new Error((data && data.error) || `Request failed (${response.status})`);
    err.status = response.status;
    throw err;
  }
  return { status: response.status, data };
}

/**
 * Run (or attach to) the engine analysis of a game through Server-Sent Events.
 * onProgress({done,total,move,status}); resolves when the analysis is cached.
 */
export function analyze(gameId, depth, onProgress) {
  return new Promise((resolve, reject) => {
    const source = new EventSource(`/api/analyze/stream?game_id=${gameId}&depth=${depth}`);
    let finished = false;
    source.addEventListener('progress', e => onProgress && onProgress(JSON.parse(e.data)));
    source.addEventListener('done', () => { finished = true; source.close(); resolve(); });
    source.addEventListener('failed', e => {
      finished = true; source.close();
      reject(new Error(JSON.parse(e.data).error || 'Analysis failed.'));
    });
    source.onerror = () => {
      if (finished) return;
      source.close();
      reject(new Error('Lost the connection to the analysis. Reload the page to resume.'));
    };
  });
}

// ------------------------------------------------------------------ utils
export const $ = (sel, root = document) => root.querySelector(sel);

export function el(tag, attrs = {}, html = '') {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  if (html) node.innerHTML = html;
  return node;
}

export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/** "600" -> "10 min", "180+2" -> "3 | 2", "1/86400" -> "Daily" */
export function formatTimeControl(tc) {
  if (!tc) return '–';
  if (tc.includes('/')) return 'Daily';
  const [base, inc] = tc.split('+').map(Number);
  if (Number.isNaN(base)) return tc;
  const minutes = base >= 60 ? `${+(base / 60).toFixed(1)}` : `${base}s`;
  if (inc) return `${minutes} | ${inc}`;
  return base >= 60 ? `${minutes} min` : minutes;
}

export function formatClock(seconds) {
  if (seconds === null || seconds === undefined) return '';
  const s = Math.max(0, seconds);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const secText = s < 20 ? sec.toFixed(1).padStart(4, '0') : String(Math.floor(sec)).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${secText}` : `${m}:${secText}`;
}

export const store = {
  get(key, fallback = null) {
    try { return localStorage.getItem(key) ?? fallback; } catch (e) { return fallback; }
  },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* ignore */ } },
};

/** Player avatar: chess.com picture when available, otherwise an initial. */
export function avatarHTML(name, url) {
  if (url) return `<img class="avatar" src="${escapeHtml(url)}" alt="" referrerpolicy="no-referrer">`;
  return `<span class="avatar avatar-initial">${escapeHtml((name || '?')[0].toUpperCase())}</span>`;
}

const avatarCache = new Map();
export async function fetchAvatar(name) {
  if (!name || !/^[A-Za-z0-9_-]{2,40}$/.test(name)) return null;
  if (!avatarCache.has(name)) {
    avatarCache.set(name, api(`/api/player/${encodeURIComponent(name)}`)
      .then(r => r.data.avatar || null).catch(() => null));
  }
  return avatarCache.get(name);
}

// ------------------------------------------------------------ board utils
/** Legal destinations for chessground from a chess.js instance. */
export function legalDests(chess) {
  const dests = new Map();
  for (const m of chess.moves({ verbose: true })) {
    if (!dests.has(m.from)) dests.set(m.from, []);
    dests.get(m.from).push(m.to);
  }
  return dests;
}

/** Try a board move on chess.js (auto-queen). Returns the move or null. */
export function tryMove(chess, from, to) {
  // chessground may report castling as king-takes-rook
  const piece = chess.get(from);
  if (piece && piece.type === 'k') {
    const fix = { e1h1: 'g1', e1a1: 'c1', e8h8: 'g8', e8a8: 'c8' }[from + to];
    if (fix) to = fix;
  }
  try { return chess.move({ from, to, promotion: 'q' }); } catch (e) { return null; }
}

/** Square ("e4") -> {x, y} in board cells from the top-left, for an orientation. */
export function squareXY(square, orientation) {
  const file = square.charCodeAt(0) - 97, rank = Number(square[1]) - 1;
  return orientation === 'white' ? { x: file, y: 7 - rank } : { x: 7 - file, y: rank };
}

// --------------------------------------------------------------- settings
// Preferences are stored by the server (SQLite) and injected into every page.
export const settings = window.APP.settings;

/** Apply appearance settings to the document (theme, board, pieces, menu). */
export function applySettings() {
  const root = document.documentElement;
  root.dataset.theme = settings.theme;
  root.dataset.board = settings.board;
  root.dataset.pieces = settings.pieces;
  root.dataset.sound = settings.sound ? 'on' : 'off';
}

/** Change preferences: updates the page at once and saves in the background. */
export function saveSettings(patch) {
  Object.assign(settings, patch);
  applySettings();
  document.dispatchEvent(new CustomEvent('settingschange', { detail: patch }));
  return api('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch),
  }).catch(() => {});
}

/** Image of a piece ("wN", "bQ") in the chosen piece set. */
export function pieceURL(code, set = settings.pieces) {
  const ext = (window.APP.pieceSets || {})[set] || 'svg';
  return `/static/img/pieces/${set}/${code}.${ext}`;
}

/** Linked chess.com username, or null. */
export const accountName = () => (settings.account ? settings.account.username : null);

// ----------------------------------------------------------------- sound
// Wooden move sounds from the open-source Lichess "standard" set.
const SOUND_FILES = { move: 'Move', capture: 'Capture', end: 'GenericNotify' };
const sounds = {};
export function playSound(name) {
  if (!settings.sound) return;
  try {
    if (!sounds[name]) sounds[name] = new Audio(`/static/sound/${SOUND_FILES[name]}.mp3`);
    const audio = sounds[name];
    audio.currentTime = 0;
    audio.volume = name === 'end' ? 0.5 : 1;
    const playing = audio.play();
    if (playing) playing.catch(() => {});   // blocked until the first user gesture
  } catch (e) { /* no audio available */ }
}

/** Sound for a move given its SAN ("Nxe5", "Qh7#"...). */
export function playMoveSound(san) {
  if (!san) return;
  playSound(san.includes('x') ? 'capture' : 'move');
  if (san.includes('#')) setTimeout(() => playSound('end'), 180);
}

/** Label for a move from the win% it lost (same ladder as the server). */
export function labelFromLoss(loss, isBest) {
  const t = window.APP.thresholds;
  if (isBest) return 'best';
  if (loss < t.excellent) return 'excellent';
  if (loss < t.good) return 'good';
  if (loss < t.inaccuracy) return 'inaccuracy';
  if (loss < t.mistake) return 'mistake';
  return 'blunder';
}

// ----------------------------------------------------------------- arrows
// Our own arrow layer (an <svg viewBox="0 0 8 8"> over the board) instead of
// chessground's: small heads, one colour per meaning, and knight moves drawn
// as an "L" (two squares straight, then one to the side).
// Colours and meanings follow chess.com's Game Review ("What do the colored
// arrows in Game Review mean?"):
export const ARROW_COLORS = {
  idea: '#ffaa00',      // orange: the main idea of the move
  best: '#8fbf3f',      // green: a stronger move you could have played
  punish: '#eb5a4e',    // red: a threat or problem (e.g. the reply that wins material)
  reply: '#4fb0e0',     // blue: the opponent's plan or response
  hint: '#3d7fe0',      // blue: the move a hint points at (lessons and puzzles)
};

export function drawArrows(svg, arrows, orientation) {
  if (!svg) return;
  const SHAFT = 0.15, HEAD_LEN = 0.3, HEAD_HALF = 0.17, START = 0.26;
  let out = '';
  for (const arrow of arrows) {
    if (!arrow || arrow.orig === arrow.dest) continue;
    const a = squareXY(arrow.orig, orientation), b = squareXY(arrow.dest, orientation);
    const p0 = { x: a.x + 0.5, y: a.y + 0.5 }, p1 = { x: b.x + 0.5, y: b.y + 0.5 };
    const dx = Math.abs(b.x - a.x), dy = Math.abs(b.y - a.y);
    const points = [p0];
    // Knight: travel the long side first, then turn
    if ((dx === 1 && dy === 2) || (dx === 2 && dy === 1)) points.push(dy === 2 ? { x: p0.x, y: p1.y } : { x: p1.x, y: p0.y });
    points.push(p1);
    const unit = (from, to) => { const l = Math.hypot(to.x - from.x, to.y - from.y) || 1; return { x: (to.x - from.x) / l, y: (to.y - from.y) / l }; };
    const first = unit(points[0], points[1]);
    const last = unit(points[points.length - 2], points[points.length - 1]);
    const start = { x: p0.x + first.x * START, y: p0.y + first.y * START };
    const tip = { x: p1.x + last.x * 0.1, y: p1.y + last.y * 0.1 };
    const base = { x: tip.x - last.x * HEAD_LEN, y: tip.y - last.y * HEAD_LEN };
    const shaft = [start, ...points.slice(1, -1), base].map(p => `${p.x.toFixed(3)},${p.y.toFixed(3)}`).join(' ');
    const nx = -last.y * HEAD_HALF, ny = last.x * HEAD_HALF;
    const head = [[tip.x, tip.y], [base.x + nx, base.y + ny], [base.x - nx, base.y - ny]].map(p => `${p[0].toFixed(3)},${p[1].toFixed(3)}`).join(' ');
    const color = ARROW_COLORS[arrow.kind] || ARROW_COLORS.best;
    out += `<g data-kind="${arrow.kind}"><polyline points="${shaft}" fill="none" stroke="${color}" stroke-width="${SHAFT}" stroke-linecap="round" stroke-linejoin="round"/><polygon points="${head}" fill="${color}"/></g>`;
  }
  svg.innerHTML = out;
}

// ---------------------------------------------------------------- presets
export const presets = window.APP.presets || [];
export const presetById = id => presets.find(p => p.id === id) || presets.find(p => p.id === 'standard') || presets[0];
export const presetByDepth = depth => presets.find(p => p.depth === depth);

// Effort = how many engines analyse a game at the same time (speed, not quality)
export const efforts = window.APP.efforts || [];
export const effortById = id => efforts.find(e => e.id === id) || efforts[0] || { id: 'low', name: 'Low', workers: 1 };
/** Engines that run in parallel with the current effort setting. */
export const engineCount = () => effortById(settings.effort).workers;
export const enginesText = n => (n === 1 ? '1 engine' : `${n} engines in parallel`);

/** "about 35 s" / "about 9 min" for a game of `positions` positions (at the current effort). */
export function estimateTime(preset, positions = 70, workers = engineCount()) {
  // several engines share the work; they lose a little by not sharing their memory
  const seconds = (preset.seconds * positions) / (workers > 1 ? workers * 0.9 : 1);
  if (seconds < 8) return 'a few seconds';
  if (seconds < 90) return `about ${Math.round(seconds / 5) * 5} s`;
  return `about ${Math.round(seconds / 60)} min`;
}

/** Brief message at the bottom of the screen. */
export function toast(message, ms = 4500) {
  for (const old of document.querySelectorAll('.toast')) old.remove();
  const node = el('div', { class: 'toast', role: 'status' });
  node.textContent = message;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), ms);
}

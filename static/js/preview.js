// Hover preview of a game's final position: a small floating board that shows
// up while the pointer is over an opponent's name (`.opp-name`) in a games table.
import { Chessground } from '../vendor/chessground.min.js';

const HOW = {
  checkmated: 'by checkmate', resigned: 'by resignation', timeout: 'on time', abandoned: 'by abandonment',
  stalemate: 'by stalemate', repetition: 'by repetition', agreed: 'by agreement',
  insufficient: 'insufficient material', timevsinsufficient: 'timeout vs insufficient material', '50move': '50-move rule',
};

/** "White won by checkmate" from a game's result + termination. */
export function terminationText(g) {
  const t = g.termination || '';
  if (t.includes(' ')) return t;                 // already a sentence (PGN "Termination" header)
  const how = HOW[t] || '';
  if (g.result === '1-0') return `White won ${how}`.trim();
  if (g.result === '0-1') return `Black won ${how}`.trim();
  if (g.result === '1/2-1/2') return `Draw ${how}`.trim();
  return 'Final position';
}

let box = null, board = null;

function ensureBox() {
  if (box) return;
  box = document.createElement('div');
  box.className = 'game-preview';
  box.hidden = true;
  box.innerHTML = '<div class="mini-board"><div class="preview-board"></div></div><div class="caption"></div>';
  document.body.appendChild(box);
}

function place(event) {
  if (!box || box.hidden) return;
  const pad = 18, w = box.offsetWidth, h = box.offsetHeight;
  let x = event.clientX + pad, y = event.clientY - h / 2;
  if (x + w > window.innerWidth - 8) x = event.clientX - w - pad;
  y = Math.max(8, Math.min(window.innerHeight - h - 8, y));
  box.style.left = `${x}px`;
  box.style.top = `${y}px`;
}

function show(g, event) {
  ensureBox();
  box.hidden = false;
  const config = {
    fen: g.final_fen, orientation: g.hero === 'b' ? 'black' : 'white',
    viewOnly: true, coordinates: false, drawable: { enabled: false },
  };
  if (!board) board = Chessground(box.querySelector('.preview-board'), config);
  else board.set(config);
  board.redrawAll();
  box.querySelector('.caption').textContent = terminationText(g);
  place(event);
}

/**
 * Show the preview while the pointer is over a `.opp-name` inside `container`.
 * `getGame(nameElement)` returns { final_fen, hero, result, termination } (or null).
 */
export function attachGamePreview(container, getGame) {
  let current = null;
  const hide = () => { current = null; if (box) box.hidden = true; };
  container.addEventListener('mousemove', e => {
    const name = e.target.closest('.opp-name');
    if (name === current) { place(e); return; }
    current = name;
    const g = name ? getGame(name) : null;
    if (g && g.final_fen) show(g, e); else if (box) box.hidden = true;
  });
  container.addEventListener('mouseleave', hide);
  window.addEventListener('scroll', hide, true);
}

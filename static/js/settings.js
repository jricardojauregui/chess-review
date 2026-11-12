// Settings page: account, analysis level, appearance, board, pieces, sound.
import { Chessground } from '../vendor/chessground.min.js';
import {
  $, api, avatarHTML, efforts, effortById, enginesText, escapeHtml, estimateTime, pieceURL, playSound, presetById,
  presets, saveSettings, settings,
} from './common.js';
import { linkAccount } from './shell.js';

const BOARDS = {
  Classic: [['classic', 'Classic'], ['forest', 'Forest'], ['ocean', 'Ocean'], ['slate', 'Slate'], ['walnut', 'Walnut'],
            ['rose', 'Rose'], ['midnight', 'Midnight'], ['tournament', 'Tournament'], ['sand', 'Sand']],
  Wood: [['maple', 'Maple'], ['darkwalnut', 'Dark walnut'], ['cherry', 'Cherry'], ['rosewood', 'Rosewood'], ['ebony', 'Ebony']],
  Stone: [['quartz', 'Quartz'], ['marble', 'Green marble'], ['rosequartz', 'Rose quartz'],
          ['granite', 'Granite'], ['obsidian', 'Obsidian'], ['parchment', 'Parchment']],
};
// Only the sets that exist on disk are offered (Neo / Neo Wood are optional
// downloads: python scripts/fetch_pieces.py).
const PIECES = [
  ['neo', 'Neo'], ['neo_wood', 'Neo Wood'], ['cburnett', 'Standard'], ['merida', 'Merida'], ['alpha', 'Alpha'], ['california', 'California'],
  ['cardinal', 'Cardinal'], ['staunty', 'Staunty'], ['maestro', 'Maestro'], ['fresca', 'Fresca'],
  ['tatiana', 'Tatiana'], ['gioco', 'Gioco'], ['governor', 'Governor'], ['kosal', 'Kosal'],
  ['companion', 'Companion'], ['dubrovny', 'Dubrovny'], ['leipzig', 'Leipzig'], ['chessnut', 'Chessnut'],
  ['pixel', 'Pixel'], ['horsey', 'Horsey'],
].filter(([id]) => id in (window.APP.pieceSets || {}));

// ---------------------------------------------------------------- account
function paintAccount() {
  const box = $('#account-panel');
  const account = settings.account;
  if (account) {
    box.innerHTML = `<div class="account-box">
        ${avatarHTML(account.username, account.avatar)}
        <div class="who"><b>${escapeHtml(account.username)}</b>
          <span class="muted">${escapeHtml(account.name || 'Linked account')}</span></div>
        <button class="btn btn-danger" id="account-unlink">Unlink account</button>
      </div>
      <div class="hint" style="margin:10px 0 0">Unlinking keeps the analyses already saved on this computer. The app will ask which account to analyze the next time you open it.</div>`;
    $('#account-unlink').addEventListener('click', async () => {
      await api('/api/account', { method: 'DELETE' });
      location.href = '/';
    });
  } else {
    box.innerHTML = `<form id="account-form" class="row">
        <input type="text" id="account-input" placeholder="chess.com username" autocomplete="off" spellcheck="false"
               aria-label="chess.com username" style="width:260px">
        <button class="btn btn-primary" type="submit">Link account</button>
      </form>
      <div id="account-error" class="error-box" hidden></div>`;
    $('#account-form').addEventListener('submit', e => {
      e.preventDefault();
      linkAccount($('#account-input').value, $('#account-error'));
    });
  }
}

// ----------------------------------------------------------------- engine
function paintPresets() {
  $('#preset-choice').innerHTML = presets.map(p => `
    <button type="button" class="preset ${p.id === 'max' ? 'max' : ''} ${p.id === settings.engine ? 'on' : ''}"
            data-preset="${p.id}" data-cost="${p.cost}" aria-pressed="${p.id === settings.engine}">
      <span class="name">${p.name}</span>
      <span class="depth">Stockfish · depth ${p.depth}</span>
      <span class="meter" title="Time and energy">${[1, 2, 3, 4, 5].map(i => `<i class="${i <= p.cost ? 'fill' : ''}"></i>`).join('')}</span>
      <span class="time">${estimateTime(p)} per game</span>
      <span class="blurb">${p.blurb}</span>
    </button>`).join('');
  const p = presets.find(x => x.id === settings.engine) || presets[0];
  const note = $('#preset-note');
  note.classList.toggle('warn', p.cost >= 4);
  if (p.cost >= 5) {
    note.innerHTML = `<b>Heads-up:</b> Max can take ${estimateTime(p)} for an ordinary game (up to ${p.max_seconds} s per move), with the CPU working hard the whole time. Great for one important game, not for batches of 20.`;
  } else if (p.cost === 4) {
    note.innerHTML = `<b>Heads-up:</b> Deep takes ${estimateTime(p)} per game and keeps the CPU busy meanwhile. Analysing many games at this level adds up.`;
  } else {
    note.innerHTML = `Times are for a game of about 35 moves on this computer at the effort chosen below. Going deeper takes longer and uses more energy; the classifications change little beyond Standard.`;
  }
}

// ----------------------------------------------------------------- effort
function paintEfforts() {
  const level = presetById(settings.engine);
  $('#effort-choice').innerHTML = efforts.map((e, i) => `
    <button type="button" class="preset ${e.id === 'max' ? 'max' : ''} ${e.id === settings.effort ? 'on' : ''}" data-effort="${e.id}" aria-pressed="${e.id === settings.effort}">
      <span class="name">${e.name}</span>
      <span class="engines">${enginesText(e.workers)}</span>
      <span class="meter" title="CPU use">${efforts.map((_, j) => `<i class="${j <= i ? 'fill' : ''}"></i>`).join('')}</span>
      <span class="time">${estimateTime(level, 70, e.workers)} per game</span>
      <span class="blurb">${e.blurb}</span>
    </button>`).join('');
  const e = effortById(settings.effort);
  $('#effort-note').innerHTML = `<b>${e.name}</b> uses ${e.workers} CPU core${e.workers === 1 ? '' : 's'} while a game is analysed. Times are for the <b>${level.name}</b> level.`;
}

$('#effort-choice').addEventListener('click', e => {
  const button = e.target.closest('[data-effort]');
  if (!button) return;
  saveSettings({ effort: button.dataset.effort });
  paintPresets();          // the level cards show times at the chosen effort
  paintEfforts();
});

$('#preset-choice').addEventListener('click', e => {
  const button = e.target.closest('[data-preset]');
  if (!button) return;
  saveSettings({ engine: button.dataset.preset });
  paintPresets();
  paintEfforts();
});

// ------------------------------------------------------------- appearance
function paintToggles() {
  for (const b of document.querySelectorAll('[data-set]')) {
    const current = b.dataset.set === 'sound' ? (settings.sound ? 'on' : 'off') : settings[b.dataset.set];
    b.classList.toggle('on', b.dataset.value === current);
  }
}
document.addEventListener('click', e => {
  const button = e.target.closest('[data-set]');
  if (!button) return;
  const key = button.dataset.set;
  saveSettings({ [key]: key === 'sound' ? button.dataset.value === 'on' : button.dataset.value });
  paintToggles();
});
$('#sound-test').addEventListener('click', () => { playSound('move'); setTimeout(() => playSound('capture'), 350); });

// ---------------------------------------------------------- board & pieces
const preview = Chessground($('#preview-board'), {
  fen: 'r1bq1rk1/pp2bppp/2n1pn2/3p4/2PP4/2N2NP1/PP2PPBP/R1BQ1RK1 w - - 0 8',
  viewOnly: true, coordinates: false, drawable: { enabled: false },
});

function paintBoards() {
  $('#board-choice').innerHTML = Object.entries(BOARDS).map(([group, items]) =>
    `<div class="swatch-group">${group}</div><div class="swatches">${items.map(([id, name]) =>
      `<button type="button" class="swatch ${id === settings.board ? 'on' : ''}" data-board-value="${id}" aria-pressed="${id === settings.board}">
         <span class="checker" data-board-swatch="${id}"></span>${name}</button>`).join('')}</div>`).join('');
  // Each swatch shows its own colours/texture: read them from the theme's CSS rule
  for (const el of document.querySelectorAll('[data-board-swatch]')) {
    const vars = boardVars(el.dataset.boardSwatch);
    for (const [k, v] of Object.entries(vars)) el.style.setProperty(k, v);
  }
  paintCaption();
}

function paintCaption() {
  const board = Object.values(BOARDS).flat().find(([id]) => id === settings.board);
  const pieces = PIECES.find(([id]) => id === settings.pieces);
  $('#preview-caption').textContent = `${board ? board[1] : settings.board} board · ${pieces ? pieces[1] : settings.pieces} pieces`;
}

/** CSS variables a board theme defines (from the stylesheet rule html[data-board="id"]). */
function boardVars(id) {
  const out = { '--board-tex': 'none', '--tex-opacity': '0' };
  for (const sheet of document.styleSheets) {
    let rules;
    try { rules = sheet.cssRules; } catch (e) { continue; }
    for (const rule of rules) {
      if (rule.selectorText === `html[data-board="${id}"]`) {
        for (const name of rule.style) out[name] = rule.style.getPropertyValue(name);
      }
    }
  }
  return out;
}

function paintPieces() {
  $('#pieces-choice').innerHTML = PIECES.map(([id, name]) =>
    `<button type="button" class="swatch ${id === settings.pieces ? 'on' : ''}" data-pieces-value="${id}" aria-pressed="${id === settings.pieces}">
       <span class="piece-pair"><img src="${pieceURL('wN', id)}" alt=""><img src="${pieceURL('bQ', id)}" alt=""></span>${name}</button>`).join('');
}

$('#board-section').addEventListener('click', e => {
  const button = e.target.closest('button');
  if (!button) return;
  if (button.dataset.boardValue) { saveSettings({ board: button.dataset.boardValue }); paintBoards(); }
  else if (button.dataset.piecesValue) { saveSettings({ pieces: button.dataset.piecesValue }); paintPieces(); paintCaption(); }
  preview.redrawAll();
});

document.addEventListener('settingschange', paintToggles);
paintAccount();
paintPresets();
paintEfforts();
paintToggles();
paintBoards();
paintPieces();
if (location.hash === '#account') { const input = $('#account-input'); if (input) input.focus(); }
